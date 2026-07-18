from __future__ import annotations

from datetime import date

import pytest

from edgar_warehouse.application.relationship_bulk_load import (
    CandidateOutcome,
    InventoryError,
    LedgerError,
    agent_coverage_by_document_type,
    build_candidate_inventory,
    build_frozen_candidate_manifest,
    candidate_inventory_from_manifest,
    index_floor_coverage_start,
    reconcile_completion_ledger,
    reconcile_completion_ledger_batches,
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
    # Unrelated 8-Ks (items prove no 5.02) are out of Ticket 20 freeze membership.
    assert "unrelated" not in by_accession
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


def test_operator_freezes_complete_quarter_indexes_into_a_bounded_manifest() -> None:
    quarter_indexes = {
        "2024Q1": [
            _filing("proxy", "DEF 14A", cik=1, filing_date="2024-02-01"),
            _filing("outside-universe", "DEF 14A", cik=2, filing_date="2024-02-02"),
            _filing("13f", "13F-HR", cik=9, filing_date="2024-02-14"),
        ],
        "2024Q2": [
            _filing("employment", "8-K", cik=1, filing_date="2024-05-01"),
            _filing("unrelated", "8-K", cik=1, filing_date="2024-05-02"),
            _filing("13f-a", "13F-HR/A", cik=9, filing_date="2024-05-15"),
        ],
    }
    silver_filings = [
        _filing("proxy", "DEF 14A", cik=1, filing_date="2024-02-01"),
        _filing("employment", "8-K", cik=1, items="5.02", filing_date="2024-05-01"),
        _filing("unrelated", "8-K", cik=1, items="2.02", filing_date="2024-05-02"),
    ]

    manifest = build_frozen_candidate_manifest(
        quarter_indexes,
        silver_filings=silver_filings,
        release_ciks={1},
        coverage_start=date(2024, 1, 1),
        watermark=date(2024, 6, 30),
        batch_size=100,
    )

    assert manifest["coverage_start"] == "2024-01-01"
    assert manifest["watermark"] == "2024-06-30"
    assert manifest["coverage_by_document_type"]["thirteenf"]["start"] == "2024-01-01"
    assert manifest["coverage_by_document_type"]["proxy"]["baseline"] == "latest_in_band_only"
    assert [row[0] for row in manifest["quarter_index_fingerprints"]] == ["2024Q1", "2024Q2"]
    assert [row["accession_number"] for row in manifest["candidates"]] == [
        "13f", "13f-a", "employment", "proxy",
    ]
    assert manifest["cik_batches"] == [{"cik_list": "1,9"}]
    assert manifest["candidate_count"] == 4
    assert manifest["index_only_candidate_count"] == 2
    assert manifest["index_only_required_count"] == 2


def test_operator_keeps_index_only_company_candidate_for_strict_backfill() -> None:
    manifest = build_frozen_candidate_manifest(
        {"2024Q1": [_filing("missing-8k", "8-K", cik=1, filing_date="2024-02-01")]},
        silver_filings=[],
        release_ciks={1},
        coverage_start=date(2024, 1, 1),
        watermark=date(2024, 3, 31),
    )

    assert manifest["candidates"][0]["accession_number"] == "missing-8k"
    assert manifest["candidates"][0]["candidate_reason"] == "ambiguous_8k_metadata"
    assert manifest["candidates"][0]["artifact_required"] is True


def test_operator_canonicalizes_multi_registrant_accession_without_hiding_ciks() -> None:
    shared = "0001104659-13-044273"
    manifest = build_frozen_candidate_manifest(
        {"2013Q2": [
            _filing(shared, "DEFA14A", cik=20, filing_date="2013-05-23"),
            _filing(shared, "DEFA14A", cik=10, filing_date="2013-05-23"),
        ]},
        silver_filings=[_filing(shared, "DEFA14A", cik=20, filing_date="2013-05-23")],
        release_ciks={10, 20},
        coverage_start=date(2013, 5, 20),
        watermark=date(2013, 6, 30),
    )

    assert [(row["accession_number"], row["cik"]) for row in manifest["candidates"]] == [
        (shared, 20),
    ]
    assert manifest["multi_registrant_accessions"] == [{
        "accession_number": shared,
        "canonical_cik": 20,
        "indexed_ciks": [10, 20],
    }]


def test_agent_coverage_windows_use_per_form_lookbacks() -> None:
    watermark = date(2026, 7, 2)
    windows = agent_coverage_by_document_type(watermark)
    assert windows["thirteenf"]["start"] == "2023-07-02"
    assert windows["thirteenf"]["end"] == "2026-07-02"
    assert windows["proxy"]["start"] == "2021-07-02"
    assert windows["proxy"]["baseline"] == "latest_in_band_only"
    assert windows["item_502_8k"]["start"] == "2024-07-02"
    assert index_floor_coverage_start(windows) == date(2021, 7, 2)


def test_agent_thirteenf_respects_xml_floor() -> None:
    watermark = date(2015, 6, 1)
    windows = agent_coverage_by_document_type(watermark)
    # W−3y = 2012-06-01 would predate XML floor
    assert windows["thirteenf"]["start"] == "2013-05-20"
    assert index_floor_coverage_start(windows) == date(2010, 6, 1)  # proxy W−5y


def test_inventory_applies_agent_windows_and_emits_coverage_metadata() -> None:
    watermark = date(2026, 7, 2)
    filings = [
        _filing("old-13f", "13F-HR", cik=9, filing_date="2020-08-14"),  # before W−3y
        _filing("new-13f", "13F-HR", cik=9, filing_date="2024-08-14"),
        _filing("old-proxy", "DEF 14A", cik=1, filing_date="2019-05-01"),  # before W−5y
        _filing("new-proxy", "DEF 14A", cik=1, filing_date="2023-05-01"),
        _filing("old-502", "8-K", cik=1, items="5.02", filing_date="2023-01-01"),  # before W−2y
        _filing("new-502", "8-K", cik=1, items="5.02", filing_date="2025-01-01"),
        _filing("unrelated", "8-K", cik=1, items="2.02", filing_date="2025-06-01"),
    ]
    # Quarters from index floor (proxy W−5y = 2021-07-02) through watermark
    from edgar_warehouse.application.relationship_bulk_load import expected_quarters

    floor = index_floor_coverage_start(agent_coverage_by_document_type(watermark))
    quarters = {key: f"fp-{key}" for key in expected_quarters(floor, watermark)}
    inventory = build_candidate_inventory(
        filings,
        watermark=watermark,
        source_manifest_fingerprints={"company:1": "c1", "company:9": "c9"},
        quarter_index_fingerprints=quarters,
        # agent windows: omit coverage_start → product defaults
    )
    accessions = {row.accession_number for row in inventory.candidates}
    assert accessions == {"new-13f", "new-proxy", "new-502"}
    assert inventory.coverage_start == floor
    assert inventory.coverage_by_document_type["thirteenf"]["start"] == "2023-07-02"


def test_frozen_manifest_agent_windows_drop_out_of_band_forms() -> None:
    watermark = date(2026, 7, 2)
    windows = agent_coverage_by_document_type(watermark)
    floor = index_floor_coverage_start(windows)
    from edgar_warehouse.application.relationship_bulk_load import expected_quarters

    quarter_indexes = {key: [] for key in expected_quarters(floor, watermark)}
    # Inside index floor (proxy W−5y) but before 13F agent start (W−3y)
    quarter_indexes["2021Q4"] = [
        _filing("old-13f", "13F-HR", cik=9, filing_date="2021-11-14"),
    ]
    quarter_indexes["2024Q3"] = [
        _filing("new-13f", "13F-HR", cik=9, filing_date="2024-08-14"),
        _filing("new-proxy", "DEF 14A", cik=1, filing_date="2024-08-01"),
        _filing("new-502", "8-K", cik=1, filing_date="2024-08-15"),
    ]
    silver = [
        _filing("new-proxy", "DEF 14A", cik=1, filing_date="2024-08-01"),
        _filing("new-502", "8-K", cik=1, items="5.02", filing_date="2024-08-15"),
    ]
    manifest = build_frozen_candidate_manifest(
        quarter_indexes,
        silver_filings=silver,
        release_ciks={1},
        watermark=watermark,
        batch_size=50,
    )
    accessions = [row["accession_number"] for row in manifest["candidates"]]
    assert "old-13f" not in accessions
    assert set(accessions) == {"new-13f", "new-proxy", "new-502"}
    assert manifest["coverage_start"] == floor.isoformat()
    assert manifest["coverage_by_document_type"] == windows
    assert manifest["fingerprint"]


def test_global_fan_in_reconciles_every_batch_outcome_once() -> None:
    inventory = build_candidate_inventory(
        [
            _filing("proxy-a", "DEF 14A", cik=1, filing_date="2024-02-01"),
            _filing("proxy-b", "DEF 14A", cik=2, filing_date="2024-02-02"),
        ],
        coverage_start=date(2024, 1, 1),
        watermark=date(2024, 3, 31),
        source_manifest_fingerprints={"company:1": "c1", "company:2": "c2"},
        quarter_index_fingerprints={"2024Q1": "q1"},
    )
    outcomes = [
        CandidateOutcome("release", candidate.accession_number, candidate.fingerprint,
                         "applicable_loaded", f"evidence-{candidate.cik}")
        for candidate in inventory.candidates
    ]

    result = reconcile_completion_ledger_batches(
        inventory,
        [{"outcomes": [outcomes[0].__dict__]}, {"outcomes": [outcomes[1].__dict__]}],
        generation_id="release",
    )

    assert result.terminal_counts == {"applicable_loaded": 2}
