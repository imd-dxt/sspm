"""
Database migration v3 – adds scan_run_id to compliance_snapshots.

Run with:
    python -m scripts.migrate_v3
    python -m scripts.migrate_v3 --dry-run

Changes applied:
  compliance_snapshots:
    - scan_run_id    UUID  (FK → scan_runs.id, nullable)
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

_STATEMENTS = [
    "ALTER TABLE compliance_snapshots ADD COLUMN IF NOT EXISTS scan_run_id UUID REFERENCES scan_runs(id)",
    "CREATE INDEX IF NOT EXISTS ix_compliance_snapshots_scan_run_id ON compliance_snapshots (scan_run_id)",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply v3 DB migration")
    parser.add_argument("--dry-run", action="store_true", help="Print SQL without executing")
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
        print(f"\nMigration v3 complete — {len(_STATEMENTS)} statements applied.")
    except Exception as exc:
        db.rollback()
        print(f"\nERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
