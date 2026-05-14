"""
TEMPORARY DEBUG SCRIPT — DELETE AFTER USE
==========================================
Tests GitHub users fetch + audit log fetch directly using
the connector credentials stored in the database.

Usage:
    python debug_github.py
    python debug_github.py <connector_id>   # optional: target a specific connector
"""
import json
import sys
import os

# ── make sure project root is on the path ────────────────────────────────────
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT, ".env"))

import psycopg2
from utils.crypto import decrypt
from connectors.github_connector import GitHubConnector

# ── 1. connect to Postgres and load connector rows ───────────────────────────
POSTGRES_URL = os.environ.get("POSTGRES_URL", "")
if not POSTGRES_URL:
    print("[ERROR] POSTGRES_URL not found in .env")
    sys.exit(1)

# psycopg2 needs postgresql:// not postgres://
conn_str = POSTGRES_URL.replace("postgresql+asyncpg://", "postgresql://").replace("postgresql+psycopg2://", "postgresql://")

conn = psycopg2.connect(conn_str)
cur  = conn.cursor()
cur.execute("SELECT id, display_name, platform_name, credentials_encrypted, config_json FROM connectors WHERE platform_name = 'github'")
rows = cur.fetchall()
cur.close()
conn.close()

if not rows:
    print("[ERROR] No GitHub connectors found in the database.")
    sys.exit(1)

# ── 2. optionally filter by connector_id argument ────────────────────────────
target_id = sys.argv[1] if len(sys.argv) > 1 else None
if target_id:
    rows = [r for r in rows if str(r[0]) == target_id]
    if not rows:
        print(f"[ERROR] No GitHub connector with id={target_id}")
        sys.exit(1)

# ── 3. debug each connector ───────────────────────────────────────────────────
for (cid, name, platform, creds_enc, config) in rows:
    print("=" * 70)
    print(f"Connector : {name}  (id={cid})")
    print(f"Platform  : {platform}")
    print(f"Config    : {config}")

    try:
        credentials = json.loads(decrypt(creds_enc))
    except Exception as exc:
        print(f"[ERROR] Could not decrypt credentials: {exc}")
        continue

    # mask the private key for safe printing
    safe_creds = {k: (v[:12] + "…REDACTED" if k == "private_key" else v) for k, v in credentials.items()}
    print(f"Creds keys: {list(credentials.keys())}")
    print(f"Creds peek: {safe_creds}")

    # ── build connector ───────────────────────────────────────────────────────
    try:
        gh = GitHubConnector(connector_id=str(cid), credentials=credentials, config=config or {})
    except Exception as exc:
        print(f"[ERROR] Could not instantiate GitHubConnector: {exc}")
        continue

    # ── test token generation ─────────────────────────────────────────────────
    print("\n[1] Testing token generation…")
    try:
        token = gh._get_installation_token()
        print(f"    OK — token starts with: {token[:10]}…")
    except Exception as exc:
        print(f"    FAIL — {type(exc).__name__}: {exc}")

    # ── test /orgs/{org}/members ──────────────────────────────────────────────
    print("\n[2] Testing fetch_users (/orgs/{org}/members)…")
    try:
        import requests as _req
        org = config.get("org", gh._org)
        token2 = gh._get_installation_token()
        r = _req.get(
            f"https://api.github.com/orgs/{org}/members",
            headers={"Authorization": f"Bearer {token2}", "Accept": "application/vnd.github+json"},
            params={"per_page": 1},
            timeout=15,
        )
        print(f"    HTTP {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            print(f"    First page has {len(data)} member(s)")
            if data:
                print(f"    First member login: {data[0].get('login')}")
        else:
            print(f"    Response: {r.text[:300]}")
    except Exception as exc:
        print(f"    FAIL — {type(exc).__name__}: {exc}")

    # ── full fetch_users via connector method ─────────────────────────────────
    print("\n[3] Calling gh.fetch_users() (full method)…")
    try:
        users = gh.fetch_users()
        print(f"    Returned {len(users)} user(s)")
        if users:
            first = users[0]
            print(f"    First user keys : {list(first.keys())}")
            print(f"    First user login: {first.get('username') or first.get('login')}")
    except Exception as exc:
        import traceback
        print(f"    FAIL — {type(exc).__name__}: {exc}")
        traceback.print_exc()

    # ── test /orgs/{org}/audit-log ────────────────────────────────────────────
    print("\n[4] Testing fetch_audit_log (/orgs/{org}/audit-log)…")
    try:
        import requests as _req
        r2 = _req.get(
            f"https://api.github.com/orgs/{org}/audit-log",
            headers={"Authorization": f"Bearer {token2}", "Accept": "application/vnd.github+json"},
            params={"per_page": 5},
            timeout=15,
        )
        print(f"    HTTP {r2.status_code}")
        if r2.status_code == 200:
            entries = r2.json()
            print(f"    Got {len(entries)} audit log entry(ies)")
            if entries:
                print(f"    First entry action: {entries[0].get('action')}")
        else:
            print(f"    Response: {r2.text[:300]}")
    except Exception as exc:
        print(f"    FAIL — {type(exc).__name__}: {exc}")

    # ── full fetch_audit_log via connector method ─────────────────────────────
    print("\n[5] Calling gh.fetch_audit_log() (full method)…")
    try:
        logs = gh.fetch_audit_log(limit=10)
        print(f"    Returned {len(logs)} log entry(ies)")
        if logs:
            print(f"    First entry: action={logs[0].get('action')}, actor={logs[0].get('actor')}")
    except Exception as exc:
        import traceback
        print(f"    FAIL — {type(exc).__name__}: {exc}")
        traceback.print_exc()

    print()

print("=" * 70)
print("Debug complete — share the output above.")
