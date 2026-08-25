"""Drive SEC reference-catalog capture from a fixed source-name set (Ticket 23).

Single-phase, unlike ``submissions_discovery.py``: each reference catalog is
one whole-file snapshot (``company_tickers.json`` /
``company_tickers_exchange.json``), no pagination inventory to derive. Unlike
``company_facts_discovery.py``, the candidate universe here isn't a bounded
CIK set either -- it's a small, fixed set of source names (exactly two today),
so there is no manifest-building "resolve a universe" step; the manifest is
built directly from ``SUPPORTED_SOURCE_NAMES`` (or an explicit override).

Only two call sites, same as ``company_facts_discovery.py`` -- no shared
``_issue_and_drive_decision`` helper extracted here either, for the same
reason (``submissions_discovery.py``'s own docstring explains why two call
sites earns the extraction and one doesn't).

Deliberately covers only ``company_tickers``/``company_tickers_exchange`` --
the PCAOB firm registry is a third reference source
(``edgartools_sec_gateway``'s catalog list), but it arrives today only via the
operator-driven ``import-relationship-source``/``pcaob_firm_registry``
evidence-import ladder in ``warehouse_orchestrator.py``, not an auto-refetched
snapshot. That path belongs to Ticket 25 (evidence-import workflows), not
this one -- see ``source_family_registry.ReferenceCatalogPolicy``'s own
docstring for the same scoping note.

Deliberately does not touch ``warehouse_orchestrator.py``'s
``_sync_reference_data`` -- that is the legacy bypass path Ticket 27 removes
only once every source family (including this one) proves the authoritative
path; this module builds a parallel, ledger-gated path.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from edgar_warehouse.acquisition.facade import SourceFamilyPolicy, build_capture_facade
from edgar_warehouse.acquisition.ledger import (
    TERMINAL_NO_DOWNLOAD_DISPOSITIONS,
    AcquisitionLedger,
    DecisionCause,
    DecisionOwnerRole,
    FetchDecisionRequest,
    FetchDisposition,
    FetchWorkState,
    execute_source_request,
)
from edgar_warehouse.infrastructure.object_storage import StorageLocation

REFERENCE_CATALOG_DISCOVERY_SOURCE_FAMILY = "reference_catalog"

DEFAULT_LEASE_SECONDS = 300

# The only two SEC reference catalogs this family covers -- see this module's
# own docstring for why PCAOB's firm registry is deliberately excluded.
SUPPORTED_SOURCE_NAMES: tuple[str, ...] = ("company_tickers", "company_tickers_exchange")


class UnsupportedReferenceSource(RuntimeError):
    """A caller asked for a source_name this family doesn't cover."""


def _source_url(source_name: str) -> str:
    from edgar_warehouse.infrastructure.sec_client import (
        build_company_tickers_exchange_url,
        build_company_tickers_url,
    )

    if source_name == "company_tickers":
        return build_company_tickers_url()
    if source_name == "company_tickers_exchange":
        return build_company_tickers_exchange_url()
    raise UnsupportedReferenceSource(f"Unsupported reference catalog source_name: {source_name!r}")


@dataclass(frozen=True)
class ReferenceCatalogCandidate:
    """One reference catalog's whole-file snapshot."""

    source_name: str
    source_url: str

    @property
    def logical_source_key(self) -> str:
        return f"reference-catalog/{self.source_name}"


@dataclass(frozen=True)
class ReferenceCatalogManifest:
    """A counted, ordered, digested manifest of the covered source-name set."""

    universe_label: str
    candidates: tuple[ReferenceCatalogCandidate, ...]

    @property
    def candidate_count(self) -> int:
        return len(self.candidates)

    @property
    def digest(self) -> str:
        canonical = "\n".join(f"{c.source_name}|{c.source_url}" for c in self.candidates)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_reference_catalog_manifest(
    source_names: Sequence[str] | None = None, *, universe_label: str
) -> ReferenceCatalogManifest:
    """Seal the covered source-name set into an ordered manifest.

    Deduplicates by ``source_name`` and orders deterministically (sorted, not
    input order) so the digest -- and therefore ``cause_reference`` downstream
    -- is stable across replays. An explicitly empty ``source_names`` list is
    a valid, complete manifest (candidate_count=0), not an error, mirroring
    Tickets 21/22's complete-empty-scope handling -- though the real default
    (``SUPPORTED_SOURCE_NAMES``) is never empty in practice.
    """

    selected = list(source_names) if source_names is not None else list(SUPPORTED_SOURCE_NAMES)
    by_name: dict[str, ReferenceCatalogCandidate] = {}
    for name in selected:
        if name in by_name:
            continue
        by_name[name] = ReferenceCatalogCandidate(source_name=name, source_url=_source_url(name))
    ordered = tuple(by_name[key] for key in sorted(by_name))
    return ReferenceCatalogManifest(universe_label=universe_label, candidates=ordered)


def reference_catalog_candidate_id(source_name: str) -> str:
    """Deterministic candidate identity: same source_name -> same id, always.

    Deliberately NOT keyed by a per-run/per-universe label -- mirrors
    ``company_facts_candidate_id``'s own reasoning exactly: a reference
    catalog's snapshot is a standing object, not scoped to a real interval, so
    keying by anything run-derived would silently break replay-safety.
    """

    return f"reference-catalog-discovery/{source_name}"


@dataclass(frozen=True)
class ReferenceCatalogCandidateOutcome:
    candidate: ReferenceCatalogCandidate
    # decision_id/fetch_disposition are None only when the ledger itself
    # rejected the Fetch Decision -- no decision exists at all for this
    # candidate in that case.
    decision_id: str | None
    fetch_disposition: FetchDisposition | None
    fetch_state: FetchWorkState | None
    network_fetched: bool
    error: str | None

    @property
    def settled(self) -> bool:
        return (
            self.fetch_state is FetchWorkState.CAPTURED
            or self.fetch_disposition in TERMINAL_NO_DOWNLOAD_DISPOSITIONS
        )


@dataclass(frozen=True)
class ReferenceCatalogDriveResult:
    manifest: ReferenceCatalogManifest
    outcomes: tuple[ReferenceCatalogCandidateOutcome, ...]

    @property
    def interval_complete(self) -> bool:
        return all(outcome.settled for outcome in self.outcomes)

    @property
    def unsettled_source_names(self) -> tuple[str, ...]:
        return tuple(
            outcome.candidate.source_name for outcome in self.outcomes if not outcome.settled
        )


def drive_reference_catalog_manifest(
    ledger: AcquisitionLedger,
    bronze_root: StorageLocation,
    registry: Mapping[str, SourceFamilyPolicy],
    manifest: ReferenceCatalogManifest,
    *,
    worker_id: str,
    registry_version: str,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
) -> ReferenceCatalogDriveResult:
    """Issue one Fetch Decision per reference catalog and drive it through capture.

    Replay-safe the same way ``company_facts_discovery.drive_company_facts_manifest``
    is: an already-``CAPTURED`` candidate is detected via a cheap, network-free
    ``create_fetch_decision`` status check before any fetch is attempted. One
    candidate's failure is caught and recorded per-candidate so it cannot
    abort the rest of the interval.
    """

    facade = build_capture_facade(ledger, bronze_root, registry, worker_id=worker_id)
    cause_reference = f"reference-catalog-manifest:{manifest.digest}:registry:{registry_version}"
    outcomes: list[ReferenceCatalogCandidateOutcome] = []
    for candidate in manifest.candidates:
        request = FetchDecisionRequest(
            candidate_id=reference_catalog_candidate_id(candidate.source_name),
            source_family=REFERENCE_CATALOG_DISCOVERY_SOURCE_FAMILY,
            logical_source_key=candidate.logical_source_key,
            source_url=candidate.source_url,
            cause=DecisionCause.CAPTURED_DISCOVERY,
            cause_reference=cause_reference,
            disposition=FetchDisposition.FETCH_AUTHORIZED,
            blocker=None,
            next_action="FETCH_SOURCE",
            owner_role=DecisionOwnerRole.ACQUISITION_COORDINATOR,
        )
        try:
            status = ledger.create_fetch_decision(request)
        except Exception as error:  # noqa: BLE001 -- one candidate must not abort the interval
            outcomes.append(
                ReferenceCatalogCandidateOutcome(
                    candidate=candidate,
                    decision_id=None,
                    fetch_disposition=None,
                    fetch_state=None,
                    network_fetched=False,
                    error=str(error),
                )
            )
            continue

        if status.fetch_state is FetchWorkState.CAPTURED:
            outcomes.append(
                ReferenceCatalogCandidateOutcome(
                    candidate=candidate,
                    decision_id=status.decision_id,
                    fetch_disposition=status.fetch_disposition,
                    fetch_state=status.fetch_state,
                    network_fetched=False,
                    error=None,
                )
            )
            continue

        try:
            result = execute_source_request(
                ledger, request, facade, worker_id=worker_id, lease_seconds=lease_seconds
            )
            final_status = ledger.source_change_status(result.status.decision_id)
        except Exception as error:  # noqa: BLE001 -- one candidate must not abort the interval
            failed_status = ledger.source_change_status(status.decision_id)
            outcomes.append(
                ReferenceCatalogCandidateOutcome(
                    candidate=candidate,
                    decision_id=failed_status.decision_id,
                    fetch_disposition=failed_status.fetch_disposition,
                    fetch_state=failed_status.fetch_state,
                    network_fetched=True,
                    error=str(error),
                )
            )
            continue

        outcomes.append(
            ReferenceCatalogCandidateOutcome(
                candidate=candidate,
                decision_id=final_status.decision_id,
                fetch_disposition=final_status.fetch_disposition,
                fetch_state=final_status.fetch_state,
                network_fetched=True,
                error=None,
            )
        )

    return ReferenceCatalogDriveResult(manifest=manifest, outcomes=tuple(outcomes))
