"""1-hop MDM candidate-neighbor expansion (change-propagation Ticket 49).

Ticket 06 decided the incremental Affected-Key Closure for MDM is bounded
to direct ``mdm_relationship_instance`` edges -- when a source row changes,
also re-check entities with a *direct* existing relationship edge to the
resolved entity, not the whole graph and not zero expansion. This module
is one pure query: given the set of entities that actually changed in a
run, find their 1-hop neighbors. It does not recurse past one hop and does
not decide what to do with the neighbors -- that is the caller's job
(``MDMPipeline.run_all``).

Deeper multi-hop ripple effects this pass structurally misses are the MDM
Reconciliation Backstop's job (Ticket 50), not this one's.
"""

from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from edgar_warehouse.mdm.database import MdmRelationshipInstance


def find_one_hop_neighbor_entity_ids(
    session: Session, changed_entity_ids: set[str]
) -> set[str]:
    """Direct relationship neighbors of ``changed_entity_ids``, one hop only.

    Only active, non-quarantined relationship instances count as a real
    edge. An entity already in ``changed_entity_ids`` is never returned as
    its own neighbor (a self-loop or a relationship between two already-
    changed entities contributes nothing new to re-check). Cost is
    proportional to the changed set's own edge count, not the universe --
    this is one indexed query, not a graph walk.
    """

    if not changed_entity_ids:
        return set()

    rows = session.execute(
        select(
            MdmRelationshipInstance.source_entity_id,
            MdmRelationshipInstance.target_entity_id,
        )
        .where(MdmRelationshipInstance.is_active.is_(True))
        .where(MdmRelationshipInstance.quarantined.is_(False))
        .where(
            or_(
                MdmRelationshipInstance.source_entity_id.in_(changed_entity_ids),
                MdmRelationshipInstance.target_entity_id.in_(changed_entity_ids),
            )
        )
    ).all()

    neighbors: set[str] = set()
    for source_entity_id, target_entity_id in rows:
        if source_entity_id in changed_entity_ids and target_entity_id not in changed_entity_ids:
            neighbors.add(target_entity_id)
        if target_entity_id in changed_entity_ids and source_entity_id not in changed_entity_ids:
            neighbors.add(source_entity_id)
    return neighbors
