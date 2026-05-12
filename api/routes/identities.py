"""
/identities — SaaS identity analytics

Endpoints:
  GET /identities/platforms           – platforms with synced entity data
  GET /identities/summary             – user / admin / at-risk / resource counts
  GET /identities/users               – paginated user list with admin flag + finding count
  GET /identities/findings-by-resource– open findings grouped by resource_identifier
  GET /identities/graph               – nodes + edges for access map
"""
from collections import Counter, defaultdict
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from database.models import Connector, Finding, NormalizedEntity
from database.session import get_db

router = APIRouter(prefix="/identities", tags=["identities"])
DB = Annotated[Session, Depends(get_db)]

_ADMIN_ROLES = frozenset({
    "admin", "owner", "administrator", "global administrator",
    "system administrator", "maintain", "organization owner",
    "org owner", "site-admin",
})


def _role_is_admin(role: str) -> bool:
    r = role.lower()
    return any(a in r or r in a for a in _ADMIN_ROLES)


def _is_admin_entity(entity: NormalizedEntity) -> bool:
    """Heuristic admin detection from entity data_json."""
    data = entity.data_json or {}
    meta = data.get("metadata") or {}

    if entity.platform == "github" and meta.get("site_admin"):
        return True

    if entity.platform == "salesforce":
        if meta.get("is_system_admin"):
            return True
        if "administrator" in (meta.get("profile_name") or "").lower():
            return True

    if entity.platform == "entraid":
        roles = meta.get("roles") or []
        if any("admin" in str(r).lower() or "global" in str(r).lower() for r in roles):
            return True

    return False


def _build_permission_maps(
    perms: list[NormalizedEntity],
) -> tuple[set[str], dict[str, set[str]]]:
    """Return (perm_admin_ids, user_resource_ids) from permission entities.

    user_resource_ids maps grantee platform_id → set of resource identifiers
    (both resource_id and resource_name/key) that the user can access.
    """
    perm_admin_ids: set[str] = set()
    user_resource_ids: dict[str, set[str]] = defaultdict(set)

    for p in perms:
        d = p.data_json or {}
        grantee = d.get("grantee_id") or d.get("subject_id", "")
        if not grantee:
            continue
        if _role_is_admin(d.get("role") or ""):
            perm_admin_ids.add(grantee)
        rid = d.get("resource_id", "")
        rname = d.get("resource_name") or d.get("resource_key", "")
        if rid:
            user_resource_ids[grantee].add(rid)
        if rname:
            user_resource_ids[grantee].add(rname)

    return perm_admin_ids, user_resource_ids


def _compute_at_risk_users(
    users: list[NormalizedEntity],
    user_resource_ids: dict[str, set[str]],
    risky_resources: set[str],
) -> set[str]:
    """Return the set of platform_ids for users considered at risk.

    A user is at risk if:
      (a) they appear directly as a resource_identifier in open findings, OR
      (b) they have access to at least one resource that has an open finding.
    """
    at_risk: set[str] = set()
    for u in users:
        pid = u.platform_id
        d = u.data_json or {}
        username = d.get("username", pid)
        email = u.email

        if pid in risky_resources or username in risky_resources:
            at_risk.add(pid)
            continue
        if email and email in risky_resources:
            at_risk.add(pid)
            continue
        if user_resource_ids.get(pid, set()) & risky_resources:
            at_risk.add(pid)

    return at_risk


def _get_risky_resources(
    db: Session,
    platform: str,
    connector_id: str | None,
) -> set[str]:
    """Return distinct resource_identifiers that have open findings."""
    fq = db.query(Finding.resource_identifier).filter(
        Finding.platform == platform,
        Finding.status == "open",
    )
    if connector_id:
        fq = fq.filter(Finding.connector_id == connector_id)
    return {row[0] for row in fq.distinct().all()}


def _build_user_resource_maps(
    perms: list[NormalizedEntity],
) -> tuple[set[str], dict[str, set[str]], dict[str, list[dict]]]:
    """Return (perm_admin_ids, user_resource_ids, user_resources) from permissions.

    user_resources maps grantee → list of {resource_id, resource_name, role} dicts.
    user_resource_ids maps grantee → set of resource identifier strings (id + name).
    """
    perm_admin_ids: set[str] = set()
    user_resource_ids: dict[str, set[str]] = defaultdict(set)
    user_resources: dict[str, list[dict]] = defaultdict(list)

    for p in perms:
        d = p.data_json or {}
        grantee = d.get("grantee_id") or d.get("subject_id", "")
        if not grantee:
            continue
        rid = d.get("resource_id", "")
        rname = d.get("resource_name") or d.get("resource_key", "")
        user_resources[grantee].append({"resource_id": rid, "resource_name": rname, "role": d.get("role", "")})
        if rid:
            user_resource_ids[grantee].add(rid)
        if rname:
            user_resource_ids[grantee].add(rname)
        if _role_is_admin(d.get("role") or ""):
            perm_admin_ids.add(grantee)

    return perm_admin_ids, user_resource_ids, user_resources


def _user_finding_count(
    pid: str,
    username: str,
    email: str | None,
    user_resource_ids: dict[str, set[str]],
    finding_counts: dict[str, int],
) -> int:
    """Sum open findings directly on the user plus findings on their resources."""
    direct = finding_counts.get(pid, 0) or finding_counts.get(username, 0)
    if email:
        direct = direct or finding_counts.get(email, 0)
    indirect = sum(finding_counts.get(r, 0) for r in user_resource_ids.get(pid, set()))
    return direct + indirect


# ── Platforms ─────────────────────────────────────────────────────────────────

@router.get("/platforms")
def list_identity_platforms(db: DB) -> list[dict[str, Any]]:
    """Platforms that have synced entity data, joined with connector info."""
    user_counts: dict[str, int] = dict(
        db.query(NormalizedEntity.platform, func.count(NormalizedEntity.id))
        .filter(NormalizedEntity.entity_type == "user")
        .group_by(NormalizedEntity.platform)
        .all()
    )
    resource_counts: dict[str, int] = dict(
        db.query(NormalizedEntity.platform, func.count(NormalizedEntity.id))
        .filter(NormalizedEntity.entity_type == "resource")
        .group_by(NormalizedEntity.platform)
        .all()
    )

    platforms_with_data = set(user_counts) | set(resource_counts)
    if not platforms_with_data:
        return []

    connectors = (
        db.query(Connector)
        .filter(Connector.platform_name.in_(list(platforms_with_data)))
        .all()
    )

    return [
        {
            "platform": c.platform_name,
            "connector_id": c.id,
            "connector_name": c.display_name,
            "connection_ok": c.connection_ok,
            "last_sync_at": c.last_sync_at.isoformat() if c.last_sync_at else None,
            "user_count": user_counts.get(c.platform_name, 0),
            "resource_count": resource_counts.get(c.platform_name, 0),
        }
        for c in connectors
        if c.platform_name in platforms_with_data
    ]


# ── Summary ───────────────────────────────────────────────────────────────────

@router.get("/summary")
def get_identity_summary(
    db: DB,
    platform: Annotated[str, Query()],
    connector_id: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    """User / admin / at-risk / resource counts for a platform."""
    users = (
        db.query(NormalizedEntity)
        .filter(NormalizedEntity.platform == platform, NormalizedEntity.entity_type == "user")
        .all()
    )

    perms = (
        db.query(NormalizedEntity)
        .filter(NormalizedEntity.platform == platform, NormalizedEntity.entity_type == "permission")
        .all()
    )

    direct_admin_ids = {u.platform_id for u in users if _is_admin_entity(u)}
    perm_admin_ids, user_resource_ids = _build_permission_maps(perms)

    resource_count = (
        db.query(func.count(NormalizedEntity.id))
        .filter(NormalizedEntity.platform == platform, NormalizedEntity.entity_type == "resource")
        .scalar() or 0
    )

    risky_resources = _get_risky_resources(db, platform, connector_id)
    at_risk_users = _compute_at_risk_users(users, user_resource_ids, risky_resources)

    return {
        "total_users": len(users),
        "total_admins": len(direct_admin_ids | perm_admin_ids),
        "users_at_risk": len(at_risk_users),
        "total_resources": resource_count,
    }


# ── Users ─────────────────────────────────────────────────────────────────────

@router.get("/users")
def list_identity_users(
    db: DB,
    platform: Annotated[str, Query()],
    connector_id: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[dict[str, Any]]:
    """Users with admin flag, finding count, and resource list."""
    users = (
        db.query(NormalizedEntity)
        .filter(NormalizedEntity.platform == platform, NormalizedEntity.entity_type == "user")
        .all()
    )

    perms = (
        db.query(NormalizedEntity)
        .filter(NormalizedEntity.platform == platform, NormalizedEntity.entity_type == "permission")
        .all()
    )
    perm_admin_ids, user_resource_ids, user_resources = _build_user_resource_maps(perms)

    # Finding counts per resource_identifier
    fq = (
        db.query(Finding.resource_identifier, func.count(Finding.id))
        .filter(Finding.platform == platform, Finding.status == "open")
    )
    if connector_id:
        fq = fq.filter(Finding.connector_id == connector_id)
    finding_counts: dict[str, int] = dict(fq.group_by(Finding.resource_identifier).all())

    result = []
    for u in users:
        d = u.data_json or {}
        pid = u.platform_id
        username = d.get("username", pid)
        fc = _user_finding_count(pid, username, u.email, user_resource_ids, finding_counts)
        is_admin = _is_admin_entity(u) or pid in perm_admin_ids

        result.append({
            "id": u.id,
            "platform_id": pid,
            "username": username,
            "display_name": d.get("display_name") or username,
            "email": u.email,
            "is_active": d.get("is_active", True),
            "is_external": d.get("is_external", False),
            "is_admin": is_admin,
            "finding_count": fc,
            "resource_count": len(user_resources.get(pid, [])),
            "resources": user_resources.get(pid, [])[:6],
        })

    result.sort(key=lambda x: (-x["finding_count"], -int(x["is_admin"]), x["username"]))
    return result[offset: offset + limit]


# ── Resources helpers ─────────────────────────────────────────────────────────

def _is_org_entity(entity: NormalizedEntity) -> bool:
    d = entity.data_json or {}
    return bool(d.get("is_organization")) or d.get("metadata", {}).get("entity_subtype") == "organization"


def _entity_resource_type(entity: NormalizedEntity) -> str | None:
    d = entity.data_json or {}
    if entity.entity_type == "group":
        return d.get("metadata", {}).get("entity_subtype") or "group"
    return d.get("resource_type") or d.get("type")


def _fetch_finding_counts(
    db: Session, platform: str, connector_id: str | None
) -> dict[str, int]:
    fq = (
        db.query(Finding.resource_identifier, func.count(Finding.id))
        .filter(Finding.platform == platform, Finding.status == "open")
    )
    if connector_id:
        fq = fq.filter(Finding.connector_id == connector_id)
    return dict(fq.group_by(Finding.resource_identifier).all())


def _fetch_sev_counts(
    db: Session, platform: str, connector_id: str | None
) -> dict[str, dict[str, int]]:
    sfq = (
        db.query(Finding.resource_identifier, Finding.severity, func.count(Finding.id))
        .filter(Finding.platform == platform, Finding.status == "open")
    )
    if connector_id:
        sfq = sfq.filter(Finding.connector_id == connector_id)
    sev_counts: dict[str, dict[str, int]] = defaultdict(
        lambda: {"critical": 0, "high": 0, "medium": 0, "low": 0}
    )
    for rid, sev, cnt in sfq.group_by(Finding.resource_identifier, Finding.severity).all():
        if sev in sev_counts[rid]:
            sev_counts[rid][sev] = cnt
    return sev_counts


_EMPTY_SEV: dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0}


def _lookup(mapping: dict[str, Any], pid: str, name: str) -> Any:
    """Try platform_id, then name, then last path segment of platform_id."""
    short = pid.split("/")[-1] if "/" in pid else ""
    return mapping.get(pid) or mapping.get(name) or (mapping.get(short) if short else None)


# ── Resources ─────────────────────────────────────────────────────────────────

@router.get("/resources")
def list_identity_resources(
    db: DB,
    platform: Annotated[str, Query()],
    connector_id: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[dict[str, Any]]:
    """Resources with finding counts and severity breakdown.

    Includes both resource entities and group entities (teams/security groups/roles),
    excluding top-level organization nodes.
    """
    all_entities = (
        db.query(NormalizedEntity)
        .filter(
            NormalizedEntity.platform == platform,
            NormalizedEntity.entity_type.in_(["resource", "group"]),
        )
        .all()
    )
    entities = [e for e in all_entities if not _is_org_entity(e)]

    finding_counts = _fetch_finding_counts(db, platform, connector_id)
    sev_counts     = _fetch_sev_counts(db, platform, connector_id)

    result = []
    for r in entities:
        d    = r.data_json or {}
        pid  = r.platform_id
        name = d.get("name") or d.get("resource_name") or pid
        fc   = _lookup(finding_counts, pid, name) or 0
        sev  = _lookup(sev_counts, pid, name) or _EMPTY_SEV
        result.append({
            "id":            r.id,
            "platform_id":   pid,
            "name":          name,
            "resource_type": _entity_resource_type(r),
            "finding_count": fc,
            "critical":      sev["critical"],
            "high":          sev["high"],
            "medium":        sev["medium"],
            "low":           sev["low"],
        })

    result.sort(key=lambda x: (-x["finding_count"], x["name"]))
    return result[offset: offset + limit]


# ── Findings by resource ───────────────────────────────────────────────────────

@router.get("/findings-by-resource")
def findings_by_resource(
    db: DB,
    platform: Annotated[str, Query()],
    connector_id: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(le=1000)] = 25,
) -> list[dict[str, Any]]:
    """Open findings grouped by resource_identifier, sorted by count desc."""
    q = db.query(Finding).filter(Finding.platform == platform, Finding.status == "open")
    if connector_id:
        q = q.filter(Finding.connector_id == connector_id)
    findings = q.all()

    groups: dict[str, dict[str, Any]] = {}
    for f in findings:
        key = f.resource_identifier
        if key not in groups:
            groups[key] = {
                "resource_identifier": key,
                "resource_type": f.resource_type,
                "total": 0,
                "critical": 0,
                "high": 0,
                "medium": 0,
                "low": 0,
            }
        groups[key]["total"] += 1
        sev = f.severity
        if sev in groups[key]:
            groups[key][sev] += 1

    return sorted(groups.values(), key=lambda x: -x["total"])[:limit]


def _build_raw_edges(perms: list[NormalizedEntity]) -> list[tuple[str, str, str, str]]:
    """Return (grantee_id, resource_id, resource_name, role) tuples from permission entities."""
    raw_edges: list[tuple[str, str, str, str]] = []
    for p in perms:
        d = p.data_json or {}
        src = d.get("grantee_id") or d.get("subject_id", "")
        tgt = d.get("resource_id", "")
        tgt_name = d.get("resource_name") or d.get("resource_key") or tgt
        role = d.get("role", "member")
        if src and tgt:
            raw_edges.append((src, tgt, tgt_name, role))
    return raw_edges


def _build_graph_user_nodes(
    top_users: set[str],
    user_entities: dict[str, NormalizedEntity],
    admin_by_perm: set[str],
) -> list[dict]:
    """Build user node dicts for the identity graph."""
    nodes = []
    for uid in top_users:
        ent = user_entities.get(uid)
        d = (ent.data_json or {}) if ent else {}
        label = d.get("display_name") or d.get("username") or uid
        nodes.append({
            "id": f"user:{uid}",
            "type": "user",
            "platform_id": uid,
            "label": label,
            "email": ent.email if ent else None,
            "is_admin": (_is_admin_entity(ent) if ent else False) or uid in admin_by_perm,
        })
    return nodes


# ── Access graph ───────────────────────────────────────────────────────────────

@router.get("/graph")
def get_identity_graph(
    db: DB,
    platform: Annotated[str, Query()],
    connector_id: Annotated[str | None, Query()] = None,
    max_users: Annotated[int, Query(le=40)] = 30,
    max_resources: Annotated[int, Query(le=40)] = 25,
) -> dict[str, Any]:
    """Nodes and edges for the user-resource access map."""
    perms = (
        db.query(NormalizedEntity)
        .filter(NormalizedEntity.platform == platform, NormalizedEntity.entity_type == "permission")
        .all()
    )
    if not perms:
        return {"nodes": [], "edges": []}

    raw_edges = _build_raw_edges(perms)
    if not raw_edges:
        return {"nodes": [], "edges": []}

    # Limit to top-connected users/resources
    top_users = {u for u, _ in Counter(e[0] for e in raw_edges).most_common(max_users)}
    top_resources = {r for r, _ in Counter(e[1] for e in raw_edges).most_common(max_resources)}
    edges = [e for e in raw_edges if e[0] in top_users and e[1] in top_resources]

    user_entities = {
        u.platform_id: u
        for u in db.query(NormalizedEntity)
        .filter(
            NormalizedEntity.platform == platform,
            NormalizedEntity.entity_type == "user",
            NormalizedEntity.platform_id.in_(list(top_users)),
        )
        .all()
    }

    # Resolve group names so UUID targets become readable labels
    group_entities = (
        db.query(NormalizedEntity)
        .filter(
            NormalizedEntity.platform == platform,
            NormalizedEntity.entity_type == "group",
            NormalizedEntity.platform_id.in_(list(top_resources)),
        )
        .all()
    )
    group_name_map: dict[str, str] = {
        g.platform_id: (g.data_json or {}).get("name") or g.platform_id
        for g in group_entities
    }
    group_id_set = set(group_name_map)

    admin_by_perm: set[str] = {e[0] for e in edges if _role_is_admin(e[3])}
    user_nodes = _build_graph_user_nodes(top_users, user_entities, admin_by_perm)

    resource_name_map: dict[str, str] = {e[1]: e[2] for e in edges}
    for rid, name in group_name_map.items():
        if not resource_name_map.get(rid) or resource_name_map[rid] == rid:
            resource_name_map[rid] = name

    resource_nodes = [
        {
            "id": f"resource:{rid}",
            "type": "group" if rid in group_id_set else "resource",
            "platform_id": rid,
            "label": resource_name_map.get(rid, rid),
        }
        for rid in top_resources
    ]

    return {
        "nodes": user_nodes + resource_nodes,
        "edges": [
            {"source": f"user:{e[0]}", "target": f"resource:{e[1]}", "role": e[3]}
            for e in edges
        ],
    }
