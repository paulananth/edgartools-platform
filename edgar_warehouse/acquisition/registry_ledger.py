"""Version and activate the Acquisition Universe (Ticket 20).

The Source Family Registry describes *what* is currently acquired --
covered source families, their in-scope logical keys (forms), acquisition
mode, completeness policy, discovery policy, and required Silver producers.
Ticket 15/16's ``build_source_family_registry`` hardcoded this as an
in-memory Python dict, constructed fresh every process start with no
history, no activation gate, and no way to prove a coverage change is safe
before it takes effect.

This module makes the registry a versioned, database-backed ledger:

- A version starts ``'draft'`` (:meth:`SourceRegistryLedger.open_draft`),
  carrying forward the currently active version's coverage for every family
  not explicitly touched, plus whatever ``add``/``remove`` changes the
  caller declares.
- Adding coverage (``coverage_action='add'``) creates a catch-up obligation:
  the version cannot activate until every declared date through
  ``catchup_required_through_date`` has been proven caught up for that
  family (:meth:`SourceRegistryLedger.record_catchup_progress`, advanced by
  a real discovery-drive run completing for that date -- reusing the exact
  completeness signal Ticket 29 already proved live, not a new prover).
  Removing coverage (``'remove'``) needs no such proof; it only stops
  *future* acquisition at ``coverage_end_date`` and never retires facts
  already in Silver.
- :meth:`SourceRegistryLedger.activate` checks every ``'add'`` row's
  obligation. If any is unmet, the version becomes ``'activation_blocked'``
  with an explicit blocker and next action, and the previously active
  version stays authoritative -- unchanged, still returned by
  :meth:`SourceRegistryLedger.get_active_registry`. Only when every
  obligation is met does the new version become ``'active'`` and the old
  one ``'superseded'``, atomically (the partial unique index on
  ``source_registry_version`` also guards this at the database level
  against a concurrent double-activation race).
- :func:`build_active_source_family_registry` is the *only* sanctioned way
  to obtain real ``SourceFamilyPolicy`` objects (Ticket 20 bullet 5) --
  ``edgar_warehouse.acquisition.source_family_registry.build_source_family_registry``
  is retired; a caller can no longer choose a Strategy implementation
  directly, only activate/carry-forward coverage of a known family through
  this ledger.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from edgar_warehouse.acquisition.facade import SourceFamilyPolicy
from edgar_warehouse.acquisition.ledger import (
    RegistryTransitionRole,
    require_registry_owner_role,
    set_postgres_role,
)
from edgar_warehouse.acquisition.models import (
    SourceRegistryCoverageRecord,
    SourceRegistryVersionRecord,
)
from edgar_warehouse.acquisition.source_family_registry import (
    COMPANY_FACTS_SOURCE_FAMILY,
    FILING_ARTIFACT_SOURCE_FAMILY,
    REFERENCE_CATALOG_SOURCE_FAMILY,
    SUBMISSIONS_SOURCE_FAMILY,
    CompanyFactsPolicy,
    FilingArtifactPolicy,
    ReferenceCatalogPolicy,
    SubmissionsPolicy,
)

_DEFAULT_ROLE = RegistryTransitionRole.ACQUISITION_REGISTRY_OWNER


class NoActiveRegistryVersion(RuntimeError):
    """No registry version has ever activated -- nothing is in scope."""


class CoverageAlreadyDeclared(ValueError):
    """The same source family was declared more than once in one draft."""


class UnsupportedAcquisitionMode(RuntimeError):
    """A covered family declares an acquisition_mode its installed Strategy
    does not implement (Ticket 32 bullet 1: acquisition_mode gates which
    Strategy factory may serve a family, rather than being read and ignored).
    """


@dataclass(frozen=True)
class CoverageSpec:
    """One caller-declared coverage change for a draft version."""

    source_family: str
    coverage_action: str  # 'add' | 'remove'
    in_scope_forms: tuple[str, ...] = ()
    acquisition_mode: str = ""
    completeness_policy: str = ""
    discovery_policy: str = ""
    required_producers: tuple[str, ...] = ()
    coverage_start_date: date | None = None
    coverage_end_date: date | None = None
    catchup_required_through_date: date | None = None


@dataclass(frozen=True)
class RegistryCoverage:
    coverage_id: str
    source_family: str
    coverage_action: str
    in_scope_forms: tuple[str, ...]
    acquisition_mode: str
    completeness_policy: str
    discovery_policy: str
    required_producers: tuple[str, ...]
    coverage_start_date: date
    coverage_end_date: date | None
    catchup_required_through_date: date | None
    catchup_verified_through_date: date | None


@dataclass(frozen=True)
class RegistryVersion:
    version_id: str
    status: str
    blocker: str | None
    next_action: str | None
    coverage: tuple[RegistryCoverage, ...] = field(default_factory=tuple)


def _coverage_from_record(record: SourceRegistryCoverageRecord) -> RegistryCoverage:
    return RegistryCoverage(
        coverage_id=record.coverage_id,
        source_family=record.source_family,
        coverage_action=record.coverage_action,
        in_scope_forms=tuple(record.in_scope_forms or ()),
        acquisition_mode=record.acquisition_mode,
        completeness_policy=record.completeness_policy,
        discovery_policy=record.discovery_policy,
        required_producers=tuple(record.required_producers or ()),
        coverage_start_date=record.coverage_start_date,
        coverage_end_date=record.coverage_end_date,
        catchup_required_through_date=record.catchup_required_through_date,
        catchup_verified_through_date=record.catchup_verified_through_date,
    )


def _version_from_record(
    record: SourceRegistryVersionRecord, coverage: list[SourceRegistryCoverageRecord]
) -> RegistryVersion:
    return RegistryVersion(
        version_id=record.version_id,
        status=record.status,
        blocker=record.blocker,
        next_action=record.next_action,
        coverage=tuple(_coverage_from_record(c) for c in coverage),
    )


class SourceRegistryLedger:
    """Transaction boundary for versioning and activating the Acquisition Universe."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def open_draft(
        self,
        coverage_specs: list[CoverageSpec],
        *,
        operator_authorization_reference: str,
        actor_role: RegistryTransitionRole = _DEFAULT_ROLE,
    ) -> RegistryVersion:
        """Open a new draft version from declared coverage changes.

        Every family covered by the currently active version that isn't
        named in ``coverage_specs`` is carried forward unchanged
        (``coverage_action='carry_forward'``) -- a partial ``coverage_specs``
        list can never accidentally drop an already-active family.

        A ``'remove'`` spec inherits ``in_scope_forms``/``acquisition_mode``/
        ``completeness_policy``/``discovery_policy``/``required_producers``
        from the family's currently active row rather than whatever (if
        anything) the caller declared for those fields -- Ticket 32 bullet 2
        makes a removed family keep acquiring, using its real operational
        policy, until ``coverage_end_date``; an operator declaring
        ``coverage_action='remove'`` should never have to redeclare that
        policy just to schedule a stop. Falls back to the spec's own values
        if the family has no currently active row (nothing to inherit).
        """

        require_registry_owner_role(actor_role)
        seen = set()
        for spec in coverage_specs:
            if spec.source_family in seen:
                raise CoverageAlreadyDeclared(
                    f"{spec.source_family!r} declared more than once in one draft"
                )
            seen.add(spec.source_family)

        with Session(self._engine) as session, session.begin():
            set_postgres_role(session, actor_role.value)
            active = self._active_record(session)
            active_by_family: dict[str, SourceRegistryCoverageRecord] = {}
            if active is not None:
                for record in session.scalars(
                    select(SourceRegistryCoverageRecord).where(
                        SourceRegistryCoverageRecord.version_id == active.version_id
                    )
                ):
                    if record.coverage_action != "remove":
                        active_by_family[record.source_family] = record
            carried = {
                family: record
                for family, record in active_by_family.items()
                if family not in seen
            }

            version = SourceRegistryVersionRecord(
                status="draft",
                operator_authorization_reference=operator_authorization_reference,
            )
            session.add(version)
            session.flush()

            coverage_records: list[SourceRegistryCoverageRecord] = []
            for spec in coverage_specs:
                inherited = (
                    active_by_family.get(spec.source_family)
                    if spec.coverage_action == "remove"
                    else None
                )
                coverage_records.append(
                    SourceRegistryCoverageRecord(
                        version_id=version.version_id,
                        source_family=spec.source_family,
                        coverage_action=spec.coverage_action,
                        in_scope_forms=(
                            list(inherited.in_scope_forms or ())
                            if inherited is not None
                            else list(spec.in_scope_forms)
                        ),
                        acquisition_mode=(
                            inherited.acquisition_mode
                            if inherited is not None
                            else spec.acquisition_mode
                        ),
                        completeness_policy=(
                            inherited.completeness_policy
                            if inherited is not None
                            else spec.completeness_policy
                        ),
                        discovery_policy=(
                            inherited.discovery_policy
                            if inherited is not None
                            else spec.discovery_policy
                        ),
                        required_producers=(
                            list(inherited.required_producers or ())
                            if inherited is not None
                            else list(spec.required_producers)
                        ),
                        coverage_start_date=spec.coverage_start_date,
                        coverage_end_date=spec.coverage_end_date,
                        catchup_required_through_date=(
                            spec.catchup_required_through_date
                            if spec.coverage_action == "add"
                            else None
                        ),
                    )
                )
            for family, record in carried.items():
                coverage_records.append(
                    SourceRegistryCoverageRecord(
                        version_id=version.version_id,
                        source_family=family,
                        coverage_action="carry_forward",
                        in_scope_forms=list(record.in_scope_forms or ()),
                        acquisition_mode=record.acquisition_mode,
                        completeness_policy=record.completeness_policy,
                        discovery_policy=record.discovery_policy,
                        required_producers=list(record.required_producers or ()),
                        coverage_start_date=record.coverage_start_date,
                        coverage_end_date=None,
                        catchup_required_through_date=None,
                        catchup_verified_through_date=None,
                    )
                )
            session.add_all(coverage_records)
            session.flush()
            return _version_from_record(version, coverage_records)

    def record_catchup_progress(
        self,
        source_family: str,
        verified_through_date: date,
        *,
        actor_role: RegistryTransitionRole = _DEFAULT_ROLE,
    ) -> None:
        """Advance the catch-up watermark for every draft 'add' row for this family.

        Called by a real discovery-drive run after it completes a business
        date for this family -- monotonic (``GREATEST``-shaped: never moves
        backwards), and a no-op if no draft version currently declares an
        'add' for this family (most runs, most of the time).
        """

        require_registry_owner_role(actor_role)
        with Session(self._engine) as session, session.begin():
            set_postgres_role(session, actor_role.value)
            rows = session.scalars(
                select(SourceRegistryCoverageRecord)
                .join(SourceRegistryVersionRecord)
                .where(
                    SourceRegistryVersionRecord.status.in_(("draft", "activation_blocked")),
                    SourceRegistryCoverageRecord.source_family == source_family,
                    SourceRegistryCoverageRecord.coverage_action == "add",
                )
            )
            for row in rows:
                if (
                    row.catchup_verified_through_date is None
                    or row.catchup_verified_through_date < verified_through_date
                ):
                    row.catchup_verified_through_date = verified_through_date

    def activate(
        self,
        version_id: str,
        *,
        actor_role: RegistryTransitionRole = _DEFAULT_ROLE,
    ) -> RegistryVersion:
        """Activate a draft version if every 'add' coverage row's catch-up
        obligation is met; otherwise block it with an explicit reason.

        The previously active version (if any) is left exactly as it was on
        any blocked activation -- :meth:`get_active_registry` keeps
        returning it. On success, that version is superseded and this one
        becomes active, in the same transaction.
        """

        require_registry_owner_role(actor_role)
        with Session(self._engine) as session, session.begin():
            set_postgres_role(session, actor_role.value)
            version = session.get(SourceRegistryVersionRecord, version_id)
            if version is None:
                raise NoActiveRegistryVersion(f"version_id={version_id} does not exist")
            coverage = list(
                session.scalars(
                    select(SourceRegistryCoverageRecord).where(
                        SourceRegistryCoverageRecord.version_id == version_id
                    )
                )
            )

            unmet = [
                c
                for c in coverage
                if c.coverage_action == "add"
                and (
                    c.catchup_verified_through_date is None
                    or c.catchup_required_through_date is None
                    or c.catchup_verified_through_date < c.catchup_required_through_date
                )
            ]
            if unmet:
                families = ", ".join(sorted({c.source_family for c in unmet}))
                version.status = "activation_blocked"
                version.blocker = (
                    f"catch-up obligation unmet for: {families}"
                )
                version.next_action = (
                    "run discovery-drive for every sealed date through "
                    "catchup_required_through_date for the listed families, "
                    "then retry activation"
                )
                session.flush()
                return _version_from_record(version, coverage)

            previous = self._active_record(session)
            if previous is not None and previous.version_id != version_id:
                previous.status = "superseded"
                previous.superseded_at = datetime.now(UTC)
                # Flushed separately, before the new version is marked
                # active below: uq_source_registry_version_single_active is a
                # partial *index*, not a deferrable constraint (Postgres
                # cannot defer a partial unique index), so it is checked
                # immediately per statement. Setting both ORM objects' status
                # and flushing once left SQLAlchemy free to emit the two
                # UPDATEs in either order -- when the new version's UPDATE
                # landed first, both rows briefly had status='active'
                # simultaneously and Postgres rejected it outright
                # (reproduced live in tests/integration/
                # test_source_registry_postgres.py). Superseding first and
                # flushing guarantees at most one 'active' row exists at any
                # statement boundary.
                session.flush()

            version.status = "active"
            version.activated_at = datetime.now(UTC)
            version.blocker = None
            version.next_action = None
            session.flush()
            return _version_from_record(version, coverage)

    def get_active_registry(
        self, *, actor_role: RegistryTransitionRole = _DEFAULT_ROLE
    ) -> RegistryVersion | None:
        """The currently active version, or ``None`` if none has ever activated."""

        with Session(self._engine) as session:
            set_postgres_role(session, actor_role.value)
            record = self._active_record(session)
            if record is None:
                return None
            coverage = list(
                session.scalars(
                    select(SourceRegistryCoverageRecord).where(
                        SourceRegistryCoverageRecord.version_id == record.version_id
                    )
                )
            )
            return _version_from_record(record, coverage)

    def _active_record(self, session: Session) -> SourceRegistryVersionRecord | None:
        return session.scalar(
            select(SourceRegistryVersionRecord).where(
                SourceRegistryVersionRecord.status == "active"
            )
        )


_PolicyFactory = Callable[[str, "RegistryCoverage"], SourceFamilyPolicy]

# Ticket 20 bullet 5: the only place a source family name is mapped to a real
# Strategy implementation -- narrow and evidenced, not a speculative plugin
# system, since exactly one family exists today. Adding a second family means
# adding one entry here, not inventing a config-driven dispatch mechanism
# nothing yet needs. Ticket 32: each entry also names the one
# acquisition_mode its factory's Strategy actually implements -- a coverage
# row declaring anything else is a real configuration error (a family
# claiming a fetch mode nothing installed can perform), not inert metadata
# to read and ignore.
_POLICY_FACTORIES: dict[str, tuple[str, _PolicyFactory]] = {
    FILING_ARTIFACT_SOURCE_FAMILY: (
        "on_demand_fetch",
        lambda identity, coverage: FilingArtifactPolicy(
            identity=identity, completeness_policy=coverage.completeness_policy
        ),
    ),
    SUBMISSIONS_SOURCE_FAMILY: (
        # Same acquisition_mode as filing_artifact -- both Strategies fetch
        # one caller-supplied URL per call; the CIK-universe-driven fan-out
        # is the new discovery driver's concern (Ticket 21), not something
        # this Strategy or its acquisition_mode need to express.
        "on_demand_fetch",
        lambda identity, coverage: SubmissionsPolicy(
            identity=identity, completeness_policy=coverage.completeness_policy
        ),
    ),
    COMPANY_FACTS_SOURCE_FAMILY: (
        # Same acquisition_mode as submissions -- one caller-supplied URL
        # per call; the CIK-universe-driven fan-out is the discovery
        # driver's concern (Ticket 22), not this Strategy's.
        "on_demand_fetch",
        lambda identity, coverage: CompanyFactsPolicy(
            identity=identity, completeness_policy=coverage.completeness_policy
        ),
    ),
    REFERENCE_CATALOG_SOURCE_FAMILY: (
        # Same acquisition_mode as every other family here -- one
        # caller-supplied URL per call; the fixed two-source-name fan-out is
        # the discovery driver's concern (Ticket 23), not this Strategy's.
        "on_demand_fetch",
        lambda identity, coverage: ReferenceCatalogPolicy(
            identity=identity, completeness_policy=coverage.completeness_policy
        ),
    ),
}


def _coverage_in_effect(coverage: RegistryCoverage, as_of_date: date) -> bool:
    """Ticket 32 bullet 2: a 'remove'd family stays in effect until its
    declared ``coverage_end_date`` -- an explicit future boundary, not
    immediate exclusion on activation. ``coverage_end_date`` is required
    non-null for 'remove' rows (``ck_source_registry_coverage_remove_end_date``);
    a defensive ``None`` here is treated as already-ended rather than raising,
    since the database already guarantees this cannot happen for a real row.
    """

    if coverage.coverage_action != "remove":
        return True
    return coverage.coverage_end_date is not None and as_of_date < coverage.coverage_end_date


def build_active_source_family_registry(
    engine: Engine, *, identity: str, as_of_date: date | None = None
) -> dict[str, SourceFamilyPolicy]:
    """The only sanctioned way to obtain real ``SourceFamilyPolicy`` objects.

    Replaces ``source_family_registry.build_source_family_registry``'s
    unconditional in-memory dict: policies now exist only for families the
    active registry version actually covers (``'add'``/``'carry_forward'``,
    or a ``'remove'``d family whose ``coverage_end_date`` boundary hasn't
    passed yet -- Ticket 32 bullet 2), and never at all before any version
    has ever activated.

    Raises :class:`UnsupportedAcquisitionMode` if a covered family declares
    an ``acquisition_mode`` its installed Strategy factory does not
    implement (Ticket 32 bullet 1).
    """

    ledger = SourceRegistryLedger(engine)
    active = ledger.get_active_registry()
    if active is None:
        raise NoActiveRegistryVersion(
            "no Source Family Registry version has ever activated -- "
            "open and activate one before running any acquisition command"
        )
    cutoff = as_of_date or date.today()
    result: dict[str, SourceFamilyPolicy] = {}
    for coverage in active.coverage:
        if not _coverage_in_effect(coverage, cutoff):
            continue
        entry = _POLICY_FACTORIES.get(coverage.source_family)
        if entry is None:
            continue  # a covered family with no known Strategy is not yet installable here
        supported_mode, factory = entry
        if coverage.acquisition_mode != supported_mode:
            raise UnsupportedAcquisitionMode(
                f"source_family={coverage.source_family!r} declares "
                f"acquisition_mode={coverage.acquisition_mode!r}, but the only "
                f"installed Strategy for it implements {supported_mode!r}"
            )
        result[coverage.source_family] = factory(identity, coverage)
    return result


def active_in_scope_forms(
    engine: Engine, source_family: str, *, as_of_date: date | None = None
) -> frozenset[str]:
    """The active registry's declared in-scope forms for one family.

    Returns an empty set (never raises) when the family isn't covered, its
    ``'remove'`` boundary (Ticket 32 bullet 2) has passed, or no version has
    ever activated -- callers like discovery-drive should treat "no
    coverage" as "nothing is in scope", not a hard failure; sealing a daily
    index observation must not depend on the registry already existing.
    """

    ledger = SourceRegistryLedger(engine)
    active = ledger.get_active_registry()
    if active is None:
        return frozenset()
    cutoff = as_of_date or date.today()
    for coverage in active.coverage:
        if coverage.source_family == source_family and _coverage_in_effect(coverage, cutoff):
            return frozenset(coverage.in_scope_forms)
    return frozenset()


def active_family_coverage(
    engine: Engine, source_family: str, *, as_of_date: date | None = None
) -> RegistryCoverage | None:
    """The active registry's full coverage row for one family, or ``None``.

    Ticket 32: the read path for ``discovery_policy``/``required_producers``
    -- fields ``active_in_scope_forms`` doesn't expose. ``None`` (never a
    raise) when the family isn't covered, its ``'remove'`` boundary has
    passed, or no version has ever activated, matching
    ``active_in_scope_forms``'s "no coverage is not a hard failure" contract.
    """

    ledger = SourceRegistryLedger(engine)
    active = ledger.get_active_registry()
    if active is None:
        return None
    cutoff = as_of_date or date.today()
    for coverage in active.coverage:
        if coverage.source_family == source_family and _coverage_in_effect(coverage, cutoff):
            return coverage
    return None
