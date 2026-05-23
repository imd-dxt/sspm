"""
Load SOC 2 security detection rules from YAML into the database.

Usage:
    python -m scripts.load_soc2_rules
    python -m scripts.load_soc2_rules --dry-run
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from database.session import SessionLocal
from core.rules_loader import RulesLoader

RULES_FILE = Path(__file__).parent.parent / "rules" / "soc2_security_rules.yaml"


def main() -> None:
    parser = argparse.ArgumentParser(description="Load SOC 2 rules into PostgreSQL")
    parser.add_argument("--dry-run", action="store_true", help="Parse without writing to DB")
    args = parser.parse_args()

    if not RULES_FILE.exists():
        print(f"ERROR: Rules file not found: {RULES_FILE}", file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        import yaml
        with RULES_FILE.open() as f:
            data = yaml.safe_load(f)
        rules = data.get("rules", [])
        print(f"Dry run — found {len(rules)} SOC 2 rules in {RULES_FILE}:")
        for r in rules:
            print(f"  [{r.get('severity', '?'):8s}] {r.get('id', '?')} — {r.get('name', '')}")
        return

    db = SessionLocal()
    try:
        loader = RulesLoader(db)
        result = loader.load_all_soc2_rules(str(RULES_FILE.parent))
        print(
            f"SOC 2 rules loaded: "
            f"{result['inserted']} inserted, {result['updated']} updated, "
            f"{result['errors']} errors"
        )
        if result.get("error_details"):
            for err in result["error_details"]:
                print(f"  ERROR: {err}", file=sys.stderr)
    finally:
        db.close()


if __name__ == "__main__":
    main()
