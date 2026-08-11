"""Pure-logic tests for ops-cost-control ticket 05's cohort registry."""
from __future__ import annotations

import pytest

from edgar_warehouse.application import ecr_rollback_registry as registry

ACCOUNT_ID = "690839588395"
REGION = "us-east-1"
REPOSITORY = "edgartools-prod-images"


def _hexify(token: str) -> str:
    """Deterministic 64-char valid-hex string derived from an arbitrary token."""
    base = token.encode("utf-8").hex() or "0"
    return (base * (64 // len(base) + 1))[:64]


def _digest(char: str) -> str:
    return "sha256:" + _hexify(char)


def _tag(role: str, char: str) -> str:
    return f"{role}-sha-{_hexify(char)[:12]}"


def _arn(role: str, revision: int = 7) -> str:
    return f"arn:aws:ecs:us-east-1:{ACCOUNT_ID}:task-definition/edgartools-prod-{role}:{revision}"


def _role_entry(role: str, char: str, *, revision: int = 7) -> dict:
    return {
        "repository": REPOSITORY,
        "digest": _digest(char),
        "immutable_tag": _tag(role, char),
        "task_definition_arns": [_arn(role, revision)],
    }


def test_build_cohort_role_entry_accepts_a_well_formed_entry():
    entry = registry.build_cohort_role_entry(role="warehouse", **_role_entry("warehouse", "a"))
    assert entry["digest"] == _digest("a")


@pytest.mark.parametrize(
    "overrides",
    [
        {"digest": "sha256:not-hex"},
        {"digest": "abc123"},
        {"immutable_tag": "mdm-sha-aaaaaaaaaaaa"},  # wrong role prefix for warehouse
        {"task_definition_arns": []},
        {"task_definition_arns": ["not-an-arn"]},
    ],
)
def test_build_cohort_role_entry_rejects_malformed_fields(overrides):
    kwargs = _role_entry("warehouse", "a")
    kwargs.update(overrides)
    with pytest.raises(registry.InvalidCohortEntryError):
        registry.build_cohort_role_entry(role="warehouse", **kwargs)


def test_empty_registry_has_no_cohorts():
    reg = registry.empty_registry(account_id=ACCOUNT_ID, region=REGION)
    assert reg["cohorts"] == []
    assert reg["account_id"] == ACCOUNT_ID


def test_advance_registry_promotes_first_cohort_to_current():
    reg = registry.empty_registry(account_id=ACCOUNT_ID, region=REGION)
    updated = registry.advance_registry(
        reg,
        candidate_id="rc-20260811-aaaaaaaaaaaa",
        verified_at="2026-08-11T00:00:00Z",
        verification_evidence="docs/release-readiness/releases/rc-20260811-aaaaaaaaaaaa/",
        warehouse=_role_entry("warehouse", "a"),
        mdm=_role_entry("mdm", "b"),
        updated_at="2026-08-11T00:00:01Z",
    )
    assert len(updated["cohorts"]) == 1
    assert updated["cohorts"][0]["slot"] == "current"


def test_advance_registry_shifts_current_to_rollback_1_and_drops_beyond_rollback_2():
    reg = registry.empty_registry(account_id=ACCOUNT_ID, region=REGION)
    timestamps = [f"2026-08-{d:02d}T00:00:00Z" for d in range(1, 6)]
    for i, ts in enumerate(timestamps):
        reg = registry.advance_registry(
            reg,
            candidate_id=f"rc-202608{i:02d}-{'a' * 12}",
            verified_at=ts,
            verification_evidence=f"evidence-{i}",
            warehouse=_role_entry("warehouse", str(i)),
            mdm=_role_entry("mdm", str(i)),
            updated_at=ts,
        )
    assert [c["slot"] for c in reg["cohorts"]] == ["current", "rollback-1", "rollback-2"]
    assert len(reg["cohorts"]) == 3
    # The 5th (most recent) advance's cohort is current; the 3rd is rollback-2; the 1st and 2nd fell off.
    assert reg["cohorts"][0]["candidate_id"] == "rc-20260804-aaaaaaaaaaaa"
    assert reg["cohorts"][2]["candidate_id"] == "rc-20260802-aaaaaaaaaaaa"


def test_advance_registry_rejects_verified_at_not_strictly_after_current():
    reg = registry.empty_registry(account_id=ACCOUNT_ID, region=REGION)
    reg = registry.advance_registry(
        reg,
        candidate_id="rc-20260811-aaaaaaaaaaaa",
        verified_at="2026-08-11T12:00:00Z",
        verification_evidence="evidence-1",
        warehouse=_role_entry("warehouse", "a"),
        mdm=_role_entry("mdm", "b"),
        updated_at="2026-08-11T12:00:01Z",
    )
    with pytest.raises(registry.NonMonotonicAdvanceError):
        registry.advance_registry(
            reg,
            candidate_id="rc-20260811-bbbbbbbbbbbb",
            verified_at="2026-08-11T11:00:00Z",  # before the existing current
            verification_evidence="evidence-2",
            warehouse=_role_entry("warehouse", "c"),
            mdm=_role_entry("mdm", "d"),
            updated_at="2026-08-11T12:00:02Z",
        )


def test_advance_registry_never_mutates_its_input():
    reg = registry.empty_registry(account_id=ACCOUNT_ID, region=REGION)
    reg = registry.advance_registry(
        reg,
        candidate_id="rc-20260811-aaaaaaaaaaaa",
        verified_at="2026-08-11T00:00:00Z",
        verification_evidence="evidence-1",
        warehouse=_role_entry("warehouse", "a"),
        mdm=_role_entry("mdm", "b"),
        updated_at="2026-08-11T00:00:01Z",
    )
    before = len(reg["cohorts"])
    registry.advance_registry(
        reg,
        candidate_id="rc-20260812-cccccccccccc",
        verified_at="2026-08-12T00:00:00Z",
        verification_evidence="evidence-2",
        warehouse=_role_entry("warehouse", "c"),
        mdm=_role_entry("mdm", "d"),
        updated_at="2026-08-12T00:00:01Z",
    )
    assert len(reg["cohorts"]) == before  # the original `reg` object is untouched


def test_validate_registry_flags_fewer_than_three_cohorts_as_insufficient_history():
    reg = registry.empty_registry(account_id=ACCOUNT_ID, region=REGION)
    reg = registry.advance_registry(
        reg,
        candidate_id="rc-20260811-aaaaaaaaaaaa",
        verified_at="2026-08-11T00:00:00Z",
        verification_evidence="evidence-1",
        warehouse=_role_entry("warehouse", "a"),
        mdm=_role_entry("mdm", "b"),
        updated_at="2026-08-11T00:00:01Z",
    )
    findings = registry.validate_registry(reg)
    assert any(f.code == "insufficient_history" for f in findings)


def test_validate_registry_accepts_a_full_three_cohort_registry():
    reg = registry.empty_registry(account_id=ACCOUNT_ID, region=REGION)
    for i, ts in enumerate(f"2026-08-{d:02d}T00:00:00Z" for d in range(9, 12)):
        reg = registry.advance_registry(
            reg,
            candidate_id=f"rc-202608{9 + i:02d}-{'a' * 12}",
            verified_at=ts,
            verification_evidence=f"evidence-{i}",
            warehouse=_role_entry("warehouse", str(i)),
            mdm=_role_entry("mdm", str(i)),
            updated_at=ts,
        )
    assert registry.validate_registry(reg) == []


def test_validate_registry_rejects_non_dict():
    findings = registry.validate_registry("not a dict")
    assert len(findings) == 1
    assert findings[0].code == "invalid_type"


def test_protected_digests_from_registry_records_provenance_per_role_and_slot():
    reg = registry.empty_registry(account_id=ACCOUNT_ID, region=REGION)
    reg = registry.advance_registry(
        reg,
        candidate_id="rc-20260811-aaaaaaaaaaaa",
        verified_at="2026-08-11T00:00:00Z",
        verification_evidence="evidence-1",
        warehouse=_role_entry("warehouse", "a"),
        mdm=_role_entry("mdm", "b"),
        updated_at="2026-08-11T00:00:01Z",
    )
    protected = registry.protected_digests_from_registry(reg)
    assert protected[_digest("a")] == ["warehouse:current"]
    assert protected[_digest("b")] == ["mdm:current"]


def test_protected_digests_from_registry_merges_provenance_for_a_digest_shared_across_slots():
    reg = registry.empty_registry(account_id=ACCOUNT_ID, region=REGION)
    for i, ts in enumerate(f"2026-08-{d:02d}T00:00:00Z" for d in range(9, 11)):
        reg = registry.advance_registry(
            reg,
            candidate_id=f"rc-202608{9 + i:02d}-{'a' * 12}",
            verified_at=ts,
            verification_evidence=f"evidence-{i}",
            # Same warehouse digest both times -- only mdm changed.
            warehouse=_role_entry("warehouse", "shared"),
            mdm=_role_entry("mdm", str(i)),
            updated_at=ts,
        )
    protected = registry.protected_digests_from_registry(reg)
    assert sorted(protected[_digest("shared")]) == ["warehouse:current", "warehouse:rollback-1"]


def test_mirror_tag_for_produces_role_scoped_tag_names():
    assert registry.mirror_tag_for("warehouse", "current") == "retain-warehouse-current"
    assert registry.mirror_tag_for("mdm", "rollback-2") == "retain-mdm-rollback-2"


def test_mirror_tag_for_rejects_unknown_role_or_slot():
    with pytest.raises(registry.RegistryError):
        registry.mirror_tag_for("bogus", "current")
    with pytest.raises(registry.RegistryError):
        registry.mirror_tag_for("warehouse", "bogus")


def test_expected_mirror_tags_covers_every_role_and_slot_present():
    reg = registry.empty_registry(account_id=ACCOUNT_ID, region=REGION)
    reg = registry.advance_registry(
        reg,
        candidate_id="rc-20260811-aaaaaaaaaaaa",
        verified_at="2026-08-11T00:00:00Z",
        verification_evidence="evidence-1",
        warehouse=_role_entry("warehouse", "a"),
        mdm=_role_entry("mdm", "b"),
        updated_at="2026-08-11T00:00:01Z",
    )
    tags = registry.expected_mirror_tags(reg)
    assert tags == {
        "retain-warehouse-current": _digest("a"),
        "retain-mdm-current": _digest("b"),
    }
