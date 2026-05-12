"""
Load normalized (condition-based) rule packs into the database.

Usage:
    python -m scripts.load_normalized_rules
    python -m scripts.load_normalized_rules --yaml path/to/rules.yaml
    python -m scripts.load_normalized_rules --no-overwrite
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from database.session import SessionLocal
from core.normalized_rules_loader import load_rule_pack

_DEFAULT_PACKS = [
    "cis_control_6_privileged_access_rules.yaml",
    "nist_sp_800_63_4_rules.yaml",
    "iso27001_2022_privileged_access_rules.yaml",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Load normalized rule packs into PostgreSQL")
    parser.add_argument(
        "--yaml",
        action="append",
        dest="yamls",
        help="Path to a rule pack YAML (can be repeated; defaults to all 3 packs)",
    )
    parser.add_argument(
        "--no-overwrite",
        action="store_true",
        help="Skip rules that already exist in the DB",
    )
    args = parser.parse_args()

    root = Path(__file__).parent.parent
    yaml_paths = [Path(p) for p in args.yamls] if args.yamls else [root / p for p in _DEFAULT_PACKS]

    with SessionLocal() as db:
        total = 0
        for path in yaml_paths:
            if not path.exists():
                print(f"[WARN] File not found: {path}", file=sys.stderr)
                continue
            count = load_rule_pack(path, db, overwrite=not args.no_overwrite)
            print(f"  {path.name}: {count} rules loaded")
            total += count
        db.commit()

    print(f"\nTotal: {total} normalized rules loaded into database.")


if __name__ == "__main__":
    main()
