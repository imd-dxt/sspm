"""
Identity correlator – matches entities from different SaaS platforms
that represent the same real-world identity.

Phase 1: email-based exact matching.
Phase 2: Neo4j FEDERATED_IDENTITY edge creation (GraphManager.create_federated_identities_by_email).
"""
import logging
from collections import defaultdict
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.graph_manager import GraphManager

log = logging.getLogger(__name__)


class IdentityCorrelator:
    """
    Groups normalized user entities across platforms by shared email.

    Usage:
        correlator = IdentityCorrelator()
        correlator.add_entities(github_users)
        correlator.add_entities(entraid_users)
        groups = correlator.correlate()

        # Optionally persist FEDERATED_IDENTITY edges to Neo4j:
        correlator.correlate_and_write(graph_manager)
    """

    def __init__(self, graph_manager: "GraphManager | None" = None) -> None:
        self._entities: list[dict[str, Any]] = []
        self._graph_manager = graph_manager

    def add_entities(self, entities: list[dict[str, Any]]) -> None:
        users = [e for e in entities if e.get("entity_type") == "user"]
        self._entities.extend(users)
        log.debug("added_entities", extra={"count": len(users)})

    def correlate(self) -> list[dict[str, Any]]:
        """
        Return a list of identity groups.

        Each group is:
            {
                "canonical_email": "user@example.com",
                "identities": [<normalized_user>, ...]
            }

        Users without an email each get their own single-identity group.
        """
        by_email: defaultdict[str, list[dict]] = defaultdict(list)
        no_email: list[dict] = []

        for entity in self._entities:
            email = (entity.get("email") or "").strip().lower()
            if email:
                by_email[email].append(entity)
            else:
                no_email.append(entity)

        groups: list[dict[str, Any]] = []
        for email, identities in by_email.items():
            groups.append({"canonical_email": email, "identities": identities})
        for entity in no_email:
            groups.append({"canonical_email": None, "identities": [entity]})

        multi = [g for g in groups if len(g["identities"]) > 1]
        log.info(
            "correlation_done",
            extra={"total_groups": len(groups), "cross_platform_matches": len(multi)},
        )
        return groups

    def correlate_and_write(self, graph_manager: "GraphManager | None" = None) -> int:
        """
        Correlate entities by email and write FEDERATED_IDENTITY edges to Neo4j.

        Delegates to GraphManager.create_federated_identities_by_email() which
        performs the correlation directly in Neo4j (more efficient for large datasets).

        Returns the number of edges created.
        """
        gm = graph_manager or self._graph_manager
        if gm is None:
            log.warning("correlate_and_write called without a GraphManager — skipping Neo4j write")
            return 0
        return gm.create_federated_identities_by_email()
