#!/usr/bin/env python3
"""
SSPM Pipeline
=============
Flow: SaaSConnector → NormalizedEvent → Neo4jWriter → Display

Requirements:
    pip install requests neo4j

Environment variables (or edit the __main__ block):
    GITHUB_TOKEN   - GitHub personal access token (needs read:org, repo scopes)
    GITHUB_ORG     - GitHub organisation login
    NEO4J_URI      - e.g. bolt://localhost:7687
    NEO4J_USER     - Neo4j username (default: neo4j)
    NEO4J_PASS     - Neo4j password
"""

import logging
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

import requests
from neo4j import GraphDatabase, Driver

# ─── Logging ─────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("sspm")


# ─── Data Model ──────────────────────────────────────────────────────────────

@dataclass
class NormalizedEvent:
    """
    Canonical representation of any SaaS resource extracted by a connector.

    Attributes:
        source        : connector that produced this event  (e.g. "github")
        resource_type : kind of resource                   (e.g. "repo", "user", "org")
        resource_id   : unique identifier within the source
        attributes    : arbitrary key/value security-relevant properties
        relations     : list of (relation_label, target_type, target_id) tuples
    """
    source: str
    resource_type: str
    resource_id: str
    attributes: dict[str, Any] = field(default_factory=dict)
    relations: list[tuple[str, str, str]] = field(default_factory=list)


# ─── Base Connector ──────────────────────────────────────────────────────────

class SaaSConnector(ABC):
    """
    Abstract base class for SaaS security connectors.
    Implement this to add support for a new SaaS platform (e.g. GitLab, Okta).
    """

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Short identifier for this connector (e.g. 'github')."""

    @abstractmethod
    def connect(self) -> None:
        """Validate credentials and connectivity. Raise on failure."""

    @abstractmethod
    def fetch_resources(self) -> list[NormalizedEvent]:
        """Fetch all resources and return them as NormalizedEvents."""


# ─── GitHub Connector ─────────────────────────────────────────────────────────

class GitHubConnector(SaaSConnector):
    """
    Extracts organisation, repositories, and members from the GitHub API.

    Collected data per repo:
        - visibility (public/private)
        - default-branch protection: allow_force_pushes, allow_deletions,
          required PR reviews, required status checks, enforce_admins

    Collected data per member:
        - login, name, email, site_admin flag

    Relations stored:
        User  ─MEMBER_OF──► Org
        Repo  ─BELONGS_TO──► Org
    """

    BASE_URL = "https://api.github.com"

    def __init__(self, api_key: str, org: str):
        self._org = org
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })
        self._log = logging.getLogger("sspm.github")

    @property
    def source_name(self) -> str:
        return "github"

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _get(self, path: str, params: Optional[dict] = None) -> Any:
        resp = self._session.get(f"{self.BASE_URL}{path}", params=params)
        resp.raise_for_status()
        return resp.json()

    def _paginate(self, path: str, params: Optional[dict] = None) -> list:
        params = dict(params or {})
        params["per_page"] = 100
        results: list = []
        page = 1
        while True:
            params["page"] = page
            data = self._get(path, params)
            if not data:
                break
            results.extend(data)
            if len(data) < 100:
                break
            page += 1
        return results

    def _branch_protection(self, repo: str, branch: str) -> dict[str, Any]:
        """
        Returns branch protection flags.
        If no protection rule exists (404) the branch is fully open:
        force pushes and deletions are implicitly allowed.
        """
        try:
            data = self._get(f"/repos/{self._org}/{repo}/branches/{branch}/protection")
            return {
                "allow_force_pushes":       data.get("allow_force_pushes", {}).get("enabled", False),
                "allow_deletions":          data.get("allow_deletions", {}).get("enabled", False),
                "required_pr_reviews":      data.get("required_pull_request_reviews") is not None,
                "required_status_checks":   data.get("required_status_checks") is not None,
                "enforce_admins":           data.get("enforce_admins", {}).get("enabled", False),
                "branch_protected":         True,
            }
        except requests.HTTPError as exc:
            if exc.response.status_code == 404:
                # No protection rule → worst-case posture
                return {
                    "allow_force_pushes":     True,
                    "allow_deletions":        True,
                    "required_pr_reviews":    False,
                    "required_status_checks": False,
                    "enforce_admins":         False,
                    "branch_protected":       False,
                }
            raise

    # ── Resource fetchers ─────────────────────────────────────────────────────

    def _fetch_org(self) -> NormalizedEvent:
        data = self._get(f"/orgs/{self._org}")
        return NormalizedEvent(
            source=self.source_name,
            resource_type="org",
            resource_id=data["login"],
            attributes={
                "login":                    data.get("login"),
                "name":                     data.get("name"),
                "description":              data.get("description"),
                "public_repos":             data.get("public_repos"),
                "total_private_repos":      data.get("total_private_repos"),
                "two_factor_required":      data.get("two_factor_requirement_enabled"),
                "default_repo_permission":  data.get("default_repository_permission"),
                "members_can_create_repos": data.get("members_can_create_repositories"),
            },
        )

    def _fetch_members(self) -> list[NormalizedEvent]:
        raw = self._paginate(f"/orgs/{self._org}/members")
        events: list[NormalizedEvent] = []
        for m in raw:
            login = m["login"]
            try:
                profile = self._get(f"/users/{login}")
            except Exception:
                profile = m
            events.append(NormalizedEvent(
                source=self.source_name,
                resource_type="user",
                resource_id=login,
                attributes={
                    "login":        login,
                    "name":         profile.get("name"),
                    "email":        profile.get("email"),
                    "public_repos": profile.get("public_repos"),
                    "site_admin":   profile.get("site_admin", False),
                    "type":         profile.get("type", "User"),
                },
                relations=[("MEMBER_OF", "org", self._org)],
            ))
            self._log.debug("  member: %s", login)
        return events

    def _fetch_repos(self) -> list[NormalizedEvent]:
        raw = self._paginate(f"/orgs/{self._org}/repos")
        events: list[NormalizedEvent] = []
        for r in raw:
            name           = r["name"]
            default_branch = r.get("default_branch", "main")
            self._log.info("  repo: %s  (default branch: %s)", name, default_branch)
            protection = self._branch_protection(name, default_branch)
            events.append(NormalizedEvent(
                source=self.source_name,
                resource_type="repo",
                resource_id=name,
                attributes={
                    "name":           name,
                    "full_name":      r.get("full_name"),
                    "is_public":      not r.get("private", True),
                    "visibility":     r.get("visibility"),
                    "default_branch": default_branch,
                    "archived":       r.get("archived", False),
                    "fork":           r.get("fork", False),
                    "language":       r.get("language"),
                    **protection,
                },
                relations=[("BELONGS_TO", "org", self._org)],
            ))
        return events

    # ── Public API ────────────────────────────────────────────────────────────

    def connect(self) -> None:
        self._log.info("Connecting to GitHub API (org: %s) …", self._org)
        data = self._get(f"/orgs/{self._org}")
        self._log.info("Connected. Organisation: %s (%s)", data.get("login"), data.get("name"))

    def fetch_resources(self) -> list[NormalizedEvent]:
        self._log.info("Fetching resources from GitHub org '%s' …", self._org)
        events: list[NormalizedEvent] = []
        events.append(self._fetch_org())
        self._log.info("Fetching members …")
        events.extend(self._fetch_members())
        self._log.info("Fetching repositories …")
        events.extend(self._fetch_repos())
        self._log.info("Total resources fetched: %d", len(events))
        return events


# ─── Neo4j Writer ─────────────────────────────────────────────────────────────

class Neo4jWriter:
    """
    Persists NormalizedEvents as nodes and relationships in Neo4j.

    Node label  = resource_type.capitalize()  (Org, User, Repo)
    Node id     = resource_id
    Properties  = source + all attributes
    """

    def __init__(self, uri: str, user: str, password: str):
        self._driver: Driver = GraphDatabase.driver(uri, auth=(user, password))
        self._log = logging.getLogger("sspm.neo4j")

    def close(self) -> None:
        self._driver.close()

    # ── Write helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _merge_node(tx, event: NormalizedEvent) -> None:
        label = event.resource_type.capitalize()
        props: dict[str, Any] = {"id": event.resource_id, "source": event.source}
        # Flatten attributes, skipping None values
        props.update({k: v for k, v in event.attributes.items() if v is not None})
        set_clause = ", ".join(f"n.{k} = ${k}" for k in props)
        tx.run(f"MERGE (n:{label} {{id: $id}}) SET {set_clause}", **props)

    @staticmethod
    def _merge_relations(tx, event: NormalizedEvent) -> None:
        src_label = event.resource_type.capitalize()
        for rel_label, tgt_type, tgt_id in event.relations:
            tgt_label = tgt_type.capitalize()
            tx.run(
                f"MATCH  (a:{src_label} {{id: $src_id}}) "
                f"MERGE  (b:{tgt_label} {{id: $tgt_id}}) "
                f"MERGE  (a)-[:{rel_label}]->(b)",
                src_id=event.resource_id,
                tgt_id=tgt_id,
            )

    # ── Public API ────────────────────────────────────────────────────────────

    def write(self, events: list[NormalizedEvent]) -> None:
        with self._driver.session() as session:
            for event in events:
                session.execute_write(self._merge_node, event)
                if event.relations:
                    session.execute_write(self._merge_relations, event)
        self._log.info("Wrote %d node(s) to Neo4j.", len(events))

    def fetch_graph(self) -> dict[str, list]:
        """Return all nodes and relationships for display."""
        with self._driver.session() as session:
            nodes = session.run("MATCH (n) RETURN n").data()
            rels  = session.run(
                "MATCH (a)-[r]->(b) RETURN a.id AS from, type(r) AS rel, b.id AS to"
            ).data()
        return {"nodes": nodes, "relationships": rels}


# ─── Pipeline ─────────────────────────────────────────────────────────────────

class SSPMPipeline:
    """Orchestrates: connect → fetch → normalize → write → display."""

    def __init__(self, connector: SaaSConnector, writer: Neo4jWriter):
        self._connector = connector
        self._writer    = writer
        self._log       = logging.getLogger("sspm.pipeline")
        self._events:   list[NormalizedEvent] = []

    def run(self) -> None:
        self._log.info("=== SSPM Pipeline START  [source: %s] ===", self._connector.source_name)
        self._connector.connect()
        self._events = self._connector.fetch_resources()
        self._writer.write(self._events)
        self._log.info("=== SSPM Pipeline DONE ===")

    def display(self) -> None:
        """Pretty-print all extracted resources and the Neo4j graph state."""

        SEP  = "═" * 64
        SEP2 = "─" * 64

        print(f"\n{SEP}")
        print("  SSPM — EXTRACTED RESOURCES")
        print(SEP)

        # Group events by resource type
        by_type: dict[str, list[NormalizedEvent]] = {}
        for e in self._events:
            by_type.setdefault(e.resource_type, []).append(e)

        for rtype in ("org", "user", "repo"):          # preferred order
            events = by_type.pop(rtype, [])
            if not events:
                continue
            print(f"\n  [{rtype.upper()}S — {len(events)}]")
            for e in events:
                print(f"\n    ▸ {e.resource_id}  (source: {e.source})")
                for k, v in e.attributes.items():
                    flag = ""
                    # Highlight risky postures
                    if k == "allow_force_pushes" and v is True:
                        flag = "  ⚠ risky"
                    if k == "is_public" and v is True:
                        flag = "  ⚠ public"
                    if k == "branch_protected" and v is False:
                        flag = "  ⚠ unprotected"
                    print(f"      {k:35s}: {v}{flag}")
                if e.relations:
                    print(f"      {'relations':35s}:", end="")
                    for rel_label, tgt_type, tgt_id in e.relations:
                        print(f" ─[{rel_label}]→ {tgt_type}:{tgt_id}", end="")
                    print()

        # Any remaining types
        for rtype, events in by_type.items():
            print(f"\n  [{rtype.upper()}S — {len(events)}]")
            for e in events:
                print(f"    ▸ {e.resource_id}")
                for k, v in e.attributes.items():
                    print(f"      {k:35s}: {v}")

        # ── Neo4j graph state ──────────────────────────────────────────────
        print(f"\n{SEP2}")
        print("  NEO4J GRAPH STATE")
        print(SEP2)

        graph = self._writer.fetch_graph()

        print(f"\n  Nodes ({len(graph['nodes'])}):")
        for row in graph["nodes"]:
            node = dict(row["n"])
            label = None
            # neo4j-python-driver exposes labels via node object before .data()
            print(f"    • {node}")

        print(f"\n  Relationships ({len(graph['relationships'])}):")
        for rel in graph["relationships"]:
            print(f"    ({rel['from']})  ─[{rel['rel']}]→  ({rel['to']})")

        print(f"\n{SEP}\n")


# ─── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import os

    GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "ghp_your_token_here")
    GITHUB_ORG   = os.getenv("GITHUB_ORG",   "your-org-name")
    NEO4J_URI    = os.getenv("NEO4J_URI",     "bolt://localhost:7687")
    NEO4J_USER   = os.getenv("NEO4J_USER",    "neo4j")
    NEO4J_PASS   = os.getenv("NEO4J_PASS",    "password")

    connector = GitHubConnector(api_key=GITHUB_TOKEN, org=GITHUB_ORG)
    writer    = Neo4jWriter(uri=NEO4J_URI, user=NEO4J_USER, password=NEO4J_PASS)
    pipeline  = SSPMPipeline(connector=connector, writer=writer)

    try:
        pipeline.run()
        pipeline.display()
    finally:
        writer.close()
