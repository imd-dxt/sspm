"""
Database migration v2 – adds columns introduced in Phase 2.

Run with:
    python -m scripts.migrate_v2
    python -m scripts.migrate_v2 --dry-run

Changes applied:
  connectors:
    - connection_ok        BOOLEAN
    - last_sync_at         TIMESTAMPTZ
    - last_sync_error      TEXT

  findings:
    - connector_id         UUID  (FK → connectors.id)
    - connector_name       VARCHAR(256)
    - justification        TEXT
    - status_changed_at    TIMESTAMPTZ
    - llm_severity         VARCHAR(16)
    - llm_severity_reasoning TEXT
    - llm_exploitability   TEXT
    - llm_remediation      TEXT
    - llm_confidence       FLOAT
    - llm_analyzed_at      TIMESTAMPTZ
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

_STATEMENTS = [
    # ── connectors ──────────────────────────────────────────────────────────
    "ALTER TABLE connectors ADD COLUMN IF NOT EXISTS connection_ok BOOLEAN",
    "ALTER TABLE connectors ADD COLUMN IF NOT EXISTS last_sync_at  TIMESTAMPTZ",
    "ALTER TABLE connectors ADD COLUMN IF NOT EXISTS last_sync_error TEXT",

    # ── findings ─────────────────────────────────────────────────────────────
    "ALTER TABLE findings ADD COLUMN IF NOT EXISTS connector_id      UUID REFERENCES connectors(id)",
    "ALTER TABLE findings ADD COLUMN IF NOT EXISTS connector_name    VARCHAR(256)",
    "ALTER TABLE findings ADD COLUMN IF NOT EXISTS justification     TEXT",
    "ALTER TABLE findings ADD COLUMN IF NOT EXISTS status_changed_at TIMESTAMPTZ",
    "ALTER TABLE findings ADD COLUMN IF NOT EXISTS llm_severity      VARCHAR(16)",
    "ALTER TABLE findings ADD COLUMN IF NOT EXISTS llm_severity_reasoning TEXT",
    "ALTER TABLE findings ADD COLUMN IF NOT EXISTS llm_exploitability TEXT",
    "ALTER TABLE findings ADD COLUMN IF NOT EXISTS llm_remediation   TEXT",
    "ALTER TABLE findings ADD COLUMN IF NOT EXISTS llm_confidence    FLOAT",
    "ALTER TABLE findings ADD COLUMN IF NOT EXISTS llm_analyzed_at   TIMESTAMPTZ",

    # ── index for connector-scoped finding lookup ─────────────────────────────
    "CREATE INDEX IF NOT EXISTS ix_findings_connector_id ON findings (connector_id)",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply v2 DB migration")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print SQL statements without executing them",
    )
    args = parser.parse_args()

    if args.dry_run:
        print("Dry run — statements that would be executed:")
        for stmt in _STATEMENTS:
            print(f"  {stmt};")
        return

    from database.session import SessionLocal
    db = SessionLocal()
    try:
        for stmt in _STATEMENTS:
            print(f"  executing: {stmt[:80]}{'...' if len(stmt) > 80 else ''}")
            db.execute(__import__("sqlalchemy").text(stmt))
        db.commit()
        print(f"\nMigration v2 complete — {len(_STATEMENTS)} statements applied.")
    except Exception as exc:
        db.rollback()
        print(f"\nERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
