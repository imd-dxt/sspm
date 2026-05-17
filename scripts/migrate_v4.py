"""
migrate_v4.py — Add GRC report metadata columns to compliance_reports.

New columns:
  status              VARCHAR(32) NOT NULL DEFAULT 'complete'
  findings_snapshot   JSONB
  report_title        VARCHAR(256)
  platforms_assessed  JSONB
  frameworks_assessed JSONB

Run: python scripts/migrate_v4.py
"""
import os
import sys

import psycopg2

_STATEMENTS = [
    "ALTER TABLE compliance_reports ADD COLUMN IF NOT EXISTS status VARCHAR(32) NOT NULL DEFAULT 'complete'",
    "ALTER TABLE compliance_reports ADD COLUMN IF NOT EXISTS findings_snapshot JSONB",
    "ALTER TABLE compliance_reports ADD COLUMN IF NOT EXISTS report_title VARCHAR(256)",
    "ALTER TABLE compliance_reports ADD COLUMN IF NOT EXISTS platforms_assessed JSONB",
    "ALTER TABLE compliance_reports ADD COLUMN IF NOT EXISTS frameworks_assessed JSONB",
]


def main() -> None:
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)
    conn = psycopg2.connect(dsn)
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            for stmt in _STATEMENTS:
                print(f"  {stmt[:80]}…")
                cur.execute(stmt)
        conn.commit()
        print("migrate_v4: done")
    except Exception as exc:
        conn.rollback()
        print(f"migrate_v4 FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
