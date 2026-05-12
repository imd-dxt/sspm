"""
Run detection rules against the current graph and persist findings.

Usage:
    python -m scripts.run_detection
    python -m scripts.run_detection --platform github
    python -m scripts.run_detection --rule GH-1.1.1
    python -m scripts.run_detection --platform github --rule GH-1.1.1
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from database.session import SessionLocal
from core.graph_manager import GraphManager
from core.rules_engine import RulesEngine


def main() -> None:
    parser = argparse.ArgumentParser(description="Run SSPM detection rules")
    parser.add_argument("--platform", help="Filter rules by platform (e.g. 'github')")
    parser.add_argument("--rule", help="Run a single rule by ID (e.g. GH-1.1.1)")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    args = parser.parse_args()

    db = SessionLocal()
    gm = GraphManager()
    try:
        engine = RulesEngine(db=db, graph=gm)

        if args.rule:
            findings = engine.run_rule(args.rule)
            if args.json:
                print(json.dumps(
                    [
                        {
                            "id": f.id,
                            "rule_id": f.rule_id,
                            "resource_identifier": f.resource_identifier,
                            "severity": f.severity,
                            "status": f.status,
                            "first_detected": f.first_detected.isoformat(),
                            "last_detected": f.last_detected.isoformat(),
                        }
                        for f in findings
                    ],
                    indent=2,
                ))
            else:
                print(f"Rule {args.rule}: {len(findings)} open finding(s)")
                for f in findings:
                    print(f"  [{f.severity:8s}] {f.resource_identifier}")
        else:
            summary = engine.run_all_rules(platform=args.platform)
            if args.json:
                print(json.dumps(summary, indent=2))
            else:
                plat = args.platform or "all platforms"
                print(f"\nDetection run complete ({plat})")
                print(f"  Rules executed : {summary['total_rules']}")
                print(f"  New findings   : {summary['new_findings']}")
                print(f"  Updated        : {summary['updated_findings']}")
                print(f"  Total open     : {summary['total_findings']}")
                print("  By severity:")
                for sev, cnt in summary["by_severity"].items():
                    if cnt:
                        print(f"    {sev:8s}: {cnt}")
                if summary["errors"]:
                    print(f"\n  Errors ({len(summary['errors'])}):", file=sys.stderr)
                    for err in summary["errors"]:
                        print(f"    {err['rule_id']}: {err['error']}", file=sys.stderr)
                    sys.exit(1)
    finally:
        gm.close()
        db.close()


if __name__ == "__main__":
    main()
