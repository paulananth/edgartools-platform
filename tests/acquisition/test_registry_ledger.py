"""Version and activate the Acquisition Universe (Ticket 20)."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from edgar_warehouse.acquisition.ledger import (
    ProcessingTransitionRole,
    UnauthorizedTransitionRole,
    require_registry_owner_role,
)
from edgar_warehouse.acquisition.models import AcquisitionBase
from edgar_warehouse.acquisition.registry_ledger import (
    CoverageSpec,
    NoActiveRegistryVersion,
    SourceRegistryLedger,
    active_in_scope_forms,
    build_active_source_family_registry,
)
from edgar_warehouse.acquisition.source_family_registry import FilingArtifactPolicy


def _engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    AcquisitionBase.metadata.create_all(engine)
    return engine


def _filing_artifact_add(catchup_required_through_date: date) -> CoverageSpec:
    return CoverageSpec(
        source_family="filing_artifact",
        coverage_action="add",
        in_scope_forms=("3", "3/A", "4", "4/A", "5", "5/A"),
        acquisition_mode="on_demand_fetch",
        completeness_policy="non_empty_payload",
        discovery_policy="daily_index_driven",
        required_producers=("sec_raw_object",),
        coverage_start_date=date(2026, 1, 1),
        catchup_required_through_date=catchup_required_through_date,
    )


def test_open_draft_creates_add_coverage_row() -> None:
    ledger = SourceRegistryLedger(_engine())
    version = ledger.open_draft(
        [_filing_artifact_add(date(2026, 8, 21))],
        operator_authorization_reference="op-1",
    )
    assert version.status == "draft"
    assert len(version.coverage) == 1
    coverage = version.coverage[0]
    assert coverage.source_family == "filing_artifact"
    assert coverage.coverage_action == "add"
    assert coverage.in_scope_forms == ("3", "3/A", "4", "4/A", "5", "5/A")
    assert coverage.catchup_required_through_date == date(2026, 8, 21)
    assert coverage.catchup_verified_through_date is None


def test_activate_blocks_when_catchup_unmet_and_leaves_no_active_version() -> None:
    ledger = SourceRegistryLedger(_engine())
    version = ledger.open_draft(
        [_filing_artifact_add(date(2026, 8, 21))],
        operator_authorization_reference="op-1",
    )
    result = ledger.activate(version.version_id)
    assert result.status == "activation_blocked"
    assert "filing_artifact" in result.blocker
    assert result.next_action

    assert ledger.get_active_registry() is None


def test_activate_succeeds_once_catchup_is_recorded() -> None:
    ledger = SourceRegistryLedger(_engine())
    version = ledger.open_draft(
        [_filing_artifact_add(date(2026, 8, 21))],
        operator_authorization_reference="op-1",
    )
    ledger.record_catchup_progress("filing_artifact", date(2026, 8, 20))
    still_blocked = ledger.activate(version.version_id)
    assert still_blocked.status == "activation_blocked"

    ledger.record_catchup_progress("filing_artifact", date(2026, 8, 21))
    activated = ledger.activate(version.version_id)
    assert activated.status == "active"
    assert activated.blocker is None
    assert activated.next_action is None

    active = ledger.get_active_registry()
    assert active is not None
    assert active.version_id == version.version_id


def test_record_catchup_progress_is_monotonic() -> None:
    ledger = SourceRegistryLedger(_engine())
    version = ledger.open_draft(
        [_filing_artifact_add(date(2026, 8, 21))],
        operator_authorization_reference="op-1",
    )
    ledger.record_catchup_progress("filing_artifact", date(2026, 8, 21))
    ledger.record_catchup_progress("filing_artifact", date(2026, 8, 10))  # must not regress

    activated = ledger.activate(version.version_id)
    assert activated.status == "active"


def test_activate_supersedes_the_previously_active_version() -> None:
    ledger = SourceRegistryLedger(_engine())
    first = ledger.open_draft(
        [_filing_artifact_add(date(2026, 1, 2))],
        operator_authorization_reference="op-1",
    )
    ledger.record_catchup_progress("filing_artifact", date(2026, 1, 2))
    ledger.activate(first.version_id)

    second = ledger.open_draft([], operator_authorization_reference="op-2")
    activated_second = ledger.activate(second.version_id)
    assert activated_second.status == "active"

    active = ledger.get_active_registry()
    assert active.version_id == second.version_id
    # filing_artifact carried forward into the second version unchanged.
    assert {c.source_family for c in active.coverage} == {"filing_artifact"}
    assert active.coverage[0].coverage_action == "carry_forward"


def test_blocked_activation_leaves_previous_active_version_untouched() -> None:
    ledger = SourceRegistryLedger(_engine())
    first = ledger.open_draft(
        [_filing_artifact_add(date(2026, 1, 2))],
        operator_authorization_reference="op-1",
    )
    ledger.record_catchup_progress("filing_artifact", date(2026, 1, 2))
    ledger.activate(first.version_id)

    second = ledger.open_draft(
        [
            CoverageSpec(
                source_family="another_family",
                coverage_action="add",
                acquisition_mode="on_demand_fetch",
                completeness_policy="non_empty_payload",
                discovery_policy="daily_index_driven",
                coverage_start_date=date(2026, 2, 1),
                catchup_required_through_date=date(2026, 2, 5),
            )
        ],
        operator_authorization_reference="op-2",
    )
    blocked = ledger.activate(second.version_id)
    assert blocked.status == "activation_blocked"

    still_active = ledger.get_active_registry()
    assert still_active.version_id == first.version_id
    assert still_active.status == "active"


def test_remove_coverage_needs_no_catchup_proof() -> None:
    ledger = SourceRegistryLedger(_engine())
    version = ledger.open_draft(
        [
            CoverageSpec(
                source_family="filing_artifact",
                coverage_action="remove",
                coverage_start_date=date(2026, 1, 1),
                coverage_end_date=date(2026, 8, 24),
            )
        ],
        operator_authorization_reference="op-1",
    )
    activated = ledger.activate(version.version_id)
    assert activated.status == "active"


def test_build_active_source_family_registry_raises_before_any_activation() -> None:
    engine = _engine()
    with pytest.raises(NoActiveRegistryVersion):
        build_active_source_family_registry(engine, identity="dev@example.com")


def test_build_active_source_family_registry_constructs_real_policy() -> None:
    engine = _engine()
    ledger = SourceRegistryLedger(engine)
    version = ledger.open_draft(
        [_filing_artifact_add(date(2026, 8, 21))],
        operator_authorization_reference="op-1",
    )
    ledger.record_catchup_progress("filing_artifact", date(2026, 8, 21))
    ledger.activate(version.version_id)

    registry = build_active_source_family_registry(engine, identity="dev@example.com")
    assert registry == {"filing_artifact": FilingArtifactPolicy(identity="dev@example.com")}


def test_removed_family_excluded_from_active_registry() -> None:
    engine = _engine()
    ledger = SourceRegistryLedger(engine)
    first = ledger.open_draft(
        [_filing_artifact_add(date(2026, 1, 2))],
        operator_authorization_reference="op-1",
    )
    ledger.record_catchup_progress("filing_artifact", date(2026, 1, 2))
    ledger.activate(first.version_id)

    second = ledger.open_draft(
        [
            CoverageSpec(
                source_family="filing_artifact",
                coverage_action="remove",
                coverage_start_date=date(2026, 1, 1),
                coverage_end_date=date(2026, 2, 1),
            )
        ],
        operator_authorization_reference="op-2",
    )
    ledger.activate(second.version_id)

    registry = build_active_source_family_registry(engine, identity="dev@example.com")
    assert registry == {}


def test_active_in_scope_forms_reflects_the_active_version() -> None:
    engine = _engine()
    assert active_in_scope_forms(engine, "filing_artifact") == frozenset()

    ledger = SourceRegistryLedger(engine)
    version = ledger.open_draft(
        [_filing_artifact_add(date(2026, 8, 21))],
        operator_authorization_reference="op-1",
    )
    ledger.record_catchup_progress("filing_artifact", date(2026, 8, 21))
    ledger.activate(version.version_id)

    assert active_in_scope_forms(engine, "filing_artifact") == frozenset(
        {"3", "3/A", "4", "4/A", "5", "5/A"}
    )
    assert active_in_scope_forms(engine, "not_a_real_family") == frozenset()


def test_require_registry_owner_role_rejects_a_foreign_role_value() -> None:
    with pytest.raises(UnauthorizedTransitionRole):
        require_registry_owner_role(ProcessingTransitionRole.ACQUISITION_PROCESSOR)  # type: ignore[arg-type]
