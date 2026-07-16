from __future__ import annotations

from datetime import date

import pytest

from edgar_warehouse.application.relationship_bulk_load import (
    CandidateOutcome,
    InventoryError,
    LedgerError,
    build_candidate_inventory,
    candidate_inventory_from_manifest,
    reconcile_completion_ledger,
    select_required_accessions,
)


def _filing(accession: str, form: str, *, cik: int = 1, items: str | None = None,
            filing_date: str = "2024-05-01", report_date: str | None = None) -> dict:
    return {
        "accession_number": accession,
        "cik": cik,
        "form": form,
        "items": items,
        "filing_date": filing_date,
        "report_date": report_date,
    }


def test_inventory_is_deterministic_and_classifies_required_sources() -> None:
    filings = [
        _filing("proxy", "DEF 14A"),
        _filing("employment", "8-K", items="2.02,5.02"),
        _filing("ambiguous", "8-K", items=None),
        _filing("unrelated", "8-K", items="2.02"),
        _filing("13f", "13F-HR", cik=9, report_date="2024-03-31"),
    ]
    kwargs = {
        "watermark": date(2024, 6, 30),
        "source_manifest_fingerprints": {"company:1": "c1", "company:9": "c9"},
        "quarter_index_fingerprints": {"2024Q1": "q1", "2024Q2": "q2"},
        "coverage_start": date(2024, 1, 1),
    }

    first = build_candidate_inventory(filings, **kwargs)
    second = build_candidate_inventory(reversed(filings), **kwargs)

    assert first.fingerprint == second.fingerprint
    by_accession = {row.accession_number: row for row in first.candidates}
    assert by_accession["proxy"].candidate_reason == "proxy_filing"
    assert by_accession["employment"].candidate_reason == "item_5_02_metadata"
    assert by_accession["ambiguous"].candidate_reason == "ambiguous_8k_metadata"
    assert by_accession["unrelated"].candidate_reason == "unrelated_8k_metadata"
    assert by_accession["unrelated"].artifact_required is False
    assert by_accession["13f"].relationship_type == "INSTITUTIONAL_HOLDS"


def test_inventory_fails_closed_for_missing_quarter_or_manifest() -> None:
    filings = [_filing("13f", "13F-HR", cik=9, report_date="2024-03-31",
                       filing_date="2024-02-14")]
    with pytest.raises(InventoryError, match="quarter.*2024Q2"):
        build_candidate_inventory(
            filings,
            coverage_start=date(2024, 1, 1),
            watermark=date(2024, 6, 30),
            source_manifest_fingerprints={"company:9": "c9"},
            quarter_index_fingerprints={"2024Q1": "q1"},
        )
    with pytest.raises(InventoryError, match="company:9"):
        build_candidate_inventory(
            filings,
            coverage_start=date(2024, 1, 1),
            watermark=date(2024, 3, 31),
            source_manifest_fingerprints={},
            quarter_index_fingerprints={"2024Q1": "q1"},
        )


def test_ledger_requires_exactly_one_current_terminal_outcome() -> None:
    inventory = build_candidate_inventory(
        [_filing("proxy", "DEF 14A", filing_date="2024-02-01")],
        coverage_start=date(2024, 1, 1),
        watermark=date(2024, 3, 31),
        source_manifest_fingerprints={"company:1": "c1"},
        quarter_index_fingerprints={"2024Q1": "q1"},
    )
    candidate = inventory.candidates[0]
    outcome = CandidateOutcome(
        generation_id="generation-1",
        accession_number="proxy",
        candidate_fingerprint=candidate.fingerprint,
        status="applicable_loaded",
        evidence_fingerprint="evidence",
    )
    result = reconcile_completion_ledger(inventory, [outcome], generation_id="generation-1")
    assert result.terminal_counts == {"applicable_loaded": 1}

    with pytest.raises(LedgerError, match="duplicate"):
        reconcile_completion_ledger(inventory, [outcome, outcome], generation_id="generation-1")
    with pytest.raises(LedgerError, match="nonterminal"):
        reconcile_completion_ledger(
            inventory,
            [CandidateOutcome("generation-1", "proxy", candidate.fingerprint,
                              "unresolved", "evidence")],
            generation_id="generation-1",
        )
    with pytest.raises(LedgerError, match="stale"):
        reconcile_completion_ledger(
            inventory,
            [CandidateOutcome("generation-1", "proxy", "old", "not_applicable", "evidence")],
            generation_id="generation-1",
        )


def test_release_manifest_selects_only_required_candidates_for_the_batch() -> None:
    payload = {
        "candidates": [
            {"accession_number": "proxy", "cik": 1, "artifact_required": True},
            {"accession_number": "unrelated", "cik": 1, "artifact_required": False},
            {"accession_number": "other-batch", "cik": 2, "artifact_required": True},
        ]
    }

    assert select_required_accessions(payload, ciks={1}) == {"proxy"}

    with pytest.raises(InventoryError, match="duplicate"):
        select_required_accessions(
            {"candidates": [payload["candidates"][0], payload["candidates"][0]]},
            ciks={1},
        )


def test_frozen_manifest_batch_reconciles_through_completion_ledger() -> None:
    inventory = build_candidate_inventory(
        [_filing("proxy", "DEF 14A", filing_date="2024-02-01")],
        coverage_start=date(2024, 1, 1),
        watermark=date(2024, 3, 31),
        source_manifest_fingerprints={"company:1": "company-sha"},
        quarter_index_fingerprints={"2024Q1": "quarter-sha"},
    )
    payload = {
        "coverage_start": inventory.coverage_start.isoformat(),
        "watermark": inventory.watermark.isoformat(),
        "fingerprint": inventory.fingerprint,
        "quarter_index_fingerprints": list(inventory.quarter_index_fingerprints),
        "candidates": [
            {
                **candidate.__dict__,
                "filing_date": candidate.filing_date.isoformat(),
                "report_date": None,
            }
            for candidate in inventory.candidates
        ],
    }

    restored = candidate_inventory_from_manifest(payload, ciks={1})
    result = reconcile_completion_ledger(
        restored,
        [CandidateOutcome(
            generation_id="release-run",
            accession_number="proxy",
            candidate_fingerprint=restored.candidates[0].fingerprint,
            status="applicable_loaded",
            evidence_fingerprint="artifact-sha",
        )],
        generation_id="release-run",
    )

    assert result.inventory_fingerprint == inventory.fingerprint
    assert result.terminal_counts == {"applicable_loaded": 1}
