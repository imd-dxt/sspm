"""
Load CIS detection rules from YAML into the database.

Usage:
    python -m scripts.load_rules
    python -m scripts.load_rules --yaml path/to/rules.yaml
    python -m scripts.load_rules --dry-run
"""
import argparse
import sys
from pathlib import Path

# Allow running from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.session import SessionLocal
from core.rules_loader import RulesLoader


def main() -> None:
    parser = argparse.ArgumentParser(description="Load CIS rules into PostgreSQL")
    parser.add_argument(
        "--yaml",
        default="github_cis_rules.yaml",
        help="Path to the rules YAML file (default: github_cis_rules.yaml)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and validate rules without writing to DB",
    )
    args = parser.parse_args()

    yaml_path = Path(args.yaml)
    if not yaml_path.exists():
        print(f"ERROR: Rules file not found: {yaml_path}", file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        import yaml
        with yaml_path.open() as f:
            data = yaml.safe_load(f)
        rules = data.get("rules", [])
        print(f"Dry run — found {len(rules)} rules in {yaml_path}:")
        for r in rules:
            print(f"  [{r.get('severity', '?'):8s}] {r.get('id', '?')} — {r.get('name', '')}")
        return

    db = SessionLocal()
    try:
        loader = RulesLoader(db)
        result = loader.load_from_yaml(str(yaml_path))
        print(
            f"Loaded rules from {yaml_path}: "
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
