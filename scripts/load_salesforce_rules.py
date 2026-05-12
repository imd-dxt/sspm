"""
Load Salesforce security rules into PostgreSQL.

Usage:
    python -m scripts.load_salesforce_rules
    python -m scripts.load_salesforce_rules --dry-run
    python -m scripts.load_salesforce_rules --yaml path/to/custom_rules.yaml
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.rules_loader import RulesLoader
from database.session import SessionLocal


def main() -> None:
    parser = argparse.ArgumentParser(description="Load Salesforce security rules into the DB")
    parser.add_argument(
        "--yaml",
        default=str(Path(__file__).parent.parent / "salesforce_security_rules.yaml"),
        help="Path to the YAML rules file (default: salesforce_security_rules.yaml)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and validate the YAML without writing to the DB",
    )
    args = parser.parse_args()

    yaml_path = Path(args.yaml)
    if not yaml_path.exists():
        print(f"ERROR: Rules file not found: {yaml_path}", file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        import yaml  # type: ignore[import]
        with open(yaml_path, encoding="utf-8") as fh:
            doc = yaml.safe_load(fh)
        rules = doc.get("rules", [])
        print(f"Dry run — found {len(rules)} rules in {yaml_path.name}")
        for r in rules:
            print(f"  [{r.get('severity', '?'):8s}] {r.get('id', '?'):20s}  {r.get('name', '')}")
        return

    db = SessionLocal()
    try:
        loader = RulesLoader(db)
        result = loader.load_from_yaml(str(yaml_path))
        print(f"Loaded Salesforce rules from {yaml_path.name}")
        print(f"  Inserted : {result['inserted']}")
        print(f"  Updated  : {result['updated']}")
        print(f"  Errors   : {result['errors']}")
        if result["error_details"]:
            for err in result["error_details"]:
                print(f"    ERROR: {err}", file=sys.stderr)
    finally:
        db.close()


if __name__ == "__main__":
    main()
