"""
Manage and inspect the Jira subgraph in Neo4j.

Usage:
    python -m scripts.manage_jira_graph stats
    python -m scripts.manage_jira_graph clear
    python -m scripts.manage_jira_graph queries
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.graph_manager import GraphManager


def cmd_stats(gm: GraphManager) -> None:
    stats = gm.get_jira_graph_stats()
    if not stats:
        print("No Jira data found in Neo4j. Run a sync first.")
        return
    print("\n=== Jira Graph Statistics ===")
    print(f"  Users (JiraUser)        : {stats.get('users', 0)}")
    print(f"  Projects (JiraProject)  : {stats.get('projects', 0)}")
    print(f"  Groups (JiraGroup)      : {stats.get('groups', 0)}")
    print(f"  Apps (Application)      : {stats.get('apps', 0)}")
    print(f"  Role assignments (edges): {stats.get('role_assignments', 0)}")
    print()


def cmd_clear(gm: GraphManager) -> None:
    answer = input("WARNING: This will delete ALL Jira nodes and relationships from Neo4j.\nType 'yes' to confirm: ")
    if answer.strip().lower() != "yes":
        print("Cancelled.")
        return
    result = gm.clear_platform_data("jira")
    print(f"Deleted {result['nodes_deleted']} nodes and {result['relationships_deleted']} relationships.")


def cmd_queries() -> None:
    cypher_file = Path(__file__).parent / "neo4j_jira_queries.cypher"
    if not cypher_file.exists():
        print("Query file not found: scripts/neo4j_jira_queries.cypher")
        return
    print("\n" + "=" * 70)
    print("  Open http://localhost:7474 and paste any query below")
    print("=" * 70 + "\n")
    print(cypher_file.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage Jira Neo4j graph")
    parser.add_argument(
        "action",
        choices=["stats", "clear", "queries"],
        help=(
            "stats   — show node/relationship counts  |  "
            "clear   — delete all Jira data  |  "
            "queries — print visualization queries"
        ),
    )
    args = parser.parse_args()

    if args.action == "queries":
        cmd_queries()
        return

    gm = GraphManager()
    try:
        if args.action == "stats":
            cmd_stats(gm)
        elif args.action == "clear":
            cmd_clear(gm)
    finally:
        gm.close()


if __name__ == "__main__":
    main()
