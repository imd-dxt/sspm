"""
Standalone compliance snapshot script.

Usage:
    python -m scripts.snapshot_compliance

Takes a compliance snapshot for all platform × framework combinations
that have mapped rules, storing results in compliance_snapshots table.
"""
import sys
import os
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

# Ensure project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> None:
    from database.session import SessionLocal
    from core.compliance_engine import ComplianceEngine

    db = SessionLocal()
    try:
        log.info("Running compliance snapshot…")
        engine = ComplianceEngine()
        engine.snapshot_all(db)
        log.info("Done.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
