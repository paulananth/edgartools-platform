"""Pure recovery planning; byte/ledger verification is exercised on PG16."""

import pytest

from edgar_warehouse.mdm.clean.source_publications import (
    VerifiedPublication,
    plan_continuity,
)
from edgar_warehouse.mdm.clean.store import Conflict, canonical, digest


def publication(sequence, *, previous=None, size=10, family="golden_copy", name=None):
    name = name or f"publication-{sequence}"
    return VerifiedPublication(
        canonical(
            {
                "source_code": "fixture.golden_copy",
                "dataset_digest": "dataset-v1",
                "source_family": "fixture",
                "publication_family": family,
                "replacement_scope": "fixture",
                "publication": name,
                "sequence": sequence,
                "manifest_sha256": digest(name),
                "mode": "delta" if previous else "full",
                "verified_bytes": size,
                "predecessor": {
                    "sequence": previous.evidence["sequence"],
                    "manifest_sha256": previous.evidence["manifest_sha256"],
                }
                if previous
                else None,
            }
        )
    )


def test_selects_smaller_proven_delta_path_independent_of_delivery_order():
    old = publication(1)
    short = publication(2, previous=old)
    finish = publication(3, previous=short)
    wide = publication(3, previous=old, size=1000, name="wide-delta")
    baseline = publication(3, size=1, name="full-3")
    options = [wide, finish, short, baseline]
    plan = plan_continuity(options, previous=old, target_sequence=3)
    assert plan == plan_continuity(
        [*reversed(options), short], previous=old, target_sequence=3
    )
    assert plan["recovery_mode"] == "delta"
    assert [p["proof_digest"] for p in plan["publications"]] == [
        short.proof_digest,
        finish.proof_digest,
    ]
    # A cheaper full snapshot does not override a proven delta route.
    assert not plan["consumption_complete"] and not plan["downstream_complete"]


def test_gap_recovers_full_baseline_then_contiguous_deltas():
    old = publication(1)
    missing = publication(2, previous=old)
    broken = publication(3, previous=missing)
    baseline = publication(3, name="full-3")
    finish = publication(4, previous=baseline)
    plan = plan_continuity([broken, baseline, finish], previous=old, target_sequence=4)
    assert plan["recovery_mode"] == "full_reconciliation"
    assert [p["proof_digest"] for p in plan["publications"]] == [
        baseline.proof_digest,
        finish.proof_digest,
    ]


def test_matching_sequence_without_matching_predecessor_hash_is_gap():
    old = publication(1)
    other = publication(1, name="conflicting-1")
    delta = publication(2, previous=other)
    with pytest.raises(Conflict, match="Continuity gap"):
        plan_continuity([delta], previous=old, target_sequence=2)


def test_sibling_family_cannot_supply_fallback_or_advance():
    old = publication(1)
    sibling = publication(2, family="opencorporates")
    with pytest.raises(Conflict, match="sibling families"):
        plan_continuity([sibling], previous=old, target_sequence=2)


def test_conflicting_native_publication_is_not_arbitrarily_selected():
    old = publication(1)
    a = publication(2, previous=old)
    b = publication(2, previous=old, size=99)
    with pytest.raises(Conflict, match="Conflicting evidence"):
        plan_continuity([a, b], previous=old, target_sequence=2)


@pytest.mark.parametrize("target", [1, 0, -1, True, "2"])
def test_no_checkpoint_rewind_or_invalid_sequence(target):
    old = publication(1)
    with pytest.raises(Conflict):
        plan_continuity([publication(2)], previous=old, target_sequence=target)


def test_frozen_proof_is_not_mutated_through_returned_dictionary():
    p = publication(1)
    original = p.proof_digest
    p.evidence["sequence"] = 1000
    assert p.proof_digest == original
    assert p.evidence["sequence"] == 1


def test_native_identity_cannot_reuse_a_completed_publication_name():
    old = publication(1)
    reused = publication(2, previous=old, name=old.evidence["publication"])
    with pytest.raises(Conflict, match="Conflicting evidence"):
        plan_continuity([reused], previous=old, target_sequence=2)
