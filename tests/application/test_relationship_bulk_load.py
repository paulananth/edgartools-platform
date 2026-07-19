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
    validate_strict_release_manifest,
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


def test_preflight_strict_release_manifest_ready_report() -> None:
    from edgar_warehouse.application.relationship_bulk_load import (
        preflight_strict_release_manifest,
        summarize_release_manifest,
    )

    watermark = date(2026, 7, 2)
    windows = agent_coverage_by_document_type(watermark)
    payload = {
        "schema_version": 1,
        "coverage_start": index_floor_coverage_start(windows).isoformat(),
        "coverage_by_document_type": windows,
        "watermark": watermark.isoformat(),
        "fingerprint": "agent-fp",
        "candidates": [
            {
                "accession_number": "new-13f",
                "cik": 9,
                "form": "13F-HR",
                "filing_date": "2024-08-14",
                "fingerprint": "c-fp",
                "candidate_reason": "thirteenf_filing",
                "artifact_required": True,
            }
        ],
        "cik_batches": [{"cik_list": "9"}],
    }
    summary = summarize_release_manifest(payload)
    assert summary["candidate_count"] == 1
    assert summary["counts_by_form"]["13F-HR"] == 1
    report = preflight_strict_release_manifest(payload)
    assert report["strict_release_eligible"] is True
    assert report["disposition"] == "READY_FOR_STRICT_LOAD"
    assert report["coverage_by_document_type"]["thirteenf"]["start"] == "2023-07-02"


def test_preflight_rejects_legacy_full_window_freeze() -> None:
    from edgar_warehouse.application.relationship_bulk_load import (
        preflight_strict_release_manifest,
    )

    payload = {
        "coverage_start": "2013-05-20",
        "watermark": "2026-07-02",
        "fingerprint": "legacy",
        "candidates": [
            {
                "accession_number": "x",
                "cik": 1,
                "form": "13F-HR",
                "filing_date": "2014-01-01",
                "fingerprint": "c",
                "artifact_required": True,
            }
        ],
    }
    with pytest.raises(InventoryError, match="coverage_by_document_type"):
        preflight_strict_release_manifest(payload)


def test_ticket20_pass_claim_binds_fingerprint_watermark_and_windows() -> None:
    from edgar_warehouse.application.relationship_bulk_load import (
        build_required_relationship_bulk_load_evidence,
        format_ticket20_pass_claim,
    )

    watermark = date(2026, 7, 2)
    windows = agent_coverage_by_document_type(watermark)
    claim = format_ticket20_pass_claim(
        watermark=watermark,
        fingerprint="abc123",
        coverage_by_document_type=windows,
    )
    assert "fingerprint abc123" in claim
    assert "watermark 2026-07-02" in claim
    assert "13F [2023-07-02, 2026-07-02]" in claim
    assert "proxy [2021-07-02, 2026-07-02]" in claim
    assert "Item 5.02 / ambiguous 8-K [2024-07-02, 2026-07-02]" in claim
    assert "complete since 2013" not in claim.lower()

    attestations = {
        "warehouse": "W",
        "mdm": "M",
        "graph": "G",
        "release_data_operator": "O",
        "release_owner": "R",
    }
    evidence = build_required_relationship_bulk_load_evidence(
        generation_id="run-1",
        inventory_fingerprint="abc123",
        watermark=watermark,
        coverage_start=index_floor_coverage_start(windows),
        coverage_by_document_type=windows,
        candidate_count=100,
        terminal_counts={"applicable_loaded": 90, "not_applicable": 10},
        ledger_fingerprint="ledger-fp",
        batch_ledger_count=2,
        attestations=attestations,
        image_digest="sha256:deadbeef",
        execution_arn="arn:aws:states:…:execution:…",
    )
    assert evidence["disposition"] == "PASS"
    assert evidence["coverage_by_document_type"] == windows
    assert evidence["pass_claim"] == claim
    assert evidence["attestations"]["release_owner"] == "R"


def test_ticket20_evidence_fail_closed_when_counts_do_not_balance() -> None:
    from edgar_warehouse.application.relationship_bulk_load import (
        build_required_relationship_bulk_load_evidence,
    )

    watermark = date(2026, 7, 2)
    windows = agent_coverage_by_document_type(watermark)
    with pytest.raises(InventoryError, match="terminal_counts"):
        build_required_relationship_bulk_load_evidence(
            generation_id="run-1",
            inventory_fingerprint="fp",
            watermark=watermark,
            coverage_start=index_floor_coverage_start(windows),
            coverage_by_document_type=windows,
            candidate_count=10,
            terminal_counts={"applicable_loaded": 5},
            ledger_fingerprint="ledger-fp",
            batch_ledger_count=1,
            require_attestations=False,
        )


def test_ticket20_evidence_requires_five_attestations() -> None:
    from edgar_warehouse.application.relationship_bulk_load import (
        build_required_relationship_bulk_load_evidence,
        parse_attestations_json,
    )

    watermark = date(2026, 7, 2)
    windows = agent_coverage_by_document_type(watermark)
    with pytest.raises(InventoryError, match="missing attestations"):
        build_required_relationship_bulk_load_evidence(
            generation_id="run-1",
            inventory_fingerprint="fp",
            watermark=watermark,
            coverage_start=index_floor_coverage_start(windows),
            coverage_by_document_type=windows,
            candidate_count=1,
            terminal_counts={"applicable_loaded": 1},
            ledger_fingerprint="ledger-fp",
            batch_ledger_count=1,
            attestations={"warehouse": "only-one"},
        )
    parsed = parse_attestations_json(
        '{"warehouse":"W","mdm":"M","graph":"G",'
        '"release_data_operator":"O","release_owner":"R"}'
    )
    assert parsed["graph"] == "G"


def test_strict_release_rejects_legacy_manifest_without_coverage_map() -> None:
    payload = {
        "coverage_start": "2013-05-20",
        "watermark": "2026-07-02",
        "fingerprint": "legacy-fp",
        "candidates": [
            {
                "accession_number": "old-13f",
                "cik": 9,
                "form": "13F-HR",
                "filing_date": "2014-02-14",
                "fingerprint": "c-fp",
                "artifact_required": True,
            }
        ],
        "quarter_index_fingerprints": [["2013Q2", "q"]],
    }
    with pytest.raises(InventoryError, match="coverage_by_document_type"):
        validate_strict_release_manifest(payload)
    with pytest.raises(InventoryError, match="coverage_by_document_type"):
        candidate_inventory_from_manifest(payload, require_strict_agent_windows=True)
    # Non-strict restore still allowed for tooling that inspects old freezes.
    restored = candidate_inventory_from_manifest(payload, ciks={9})
    assert restored.fingerprint == "legacy-fp"


def test_strict_release_accepts_agent_window_manifest() -> None:
    watermark = date(2026, 7, 2)
    windows = agent_coverage_by_document_type(watermark)
    payload = {
        "coverage_start": index_floor_coverage_start(windows).isoformat(),
        "coverage_by_document_type": windows,
        "watermark": watermark.isoformat(),
        "fingerprint": "agent-fp",
        "candidates": [
            {
                "accession_number": "new-13f",
                "cik": 9,
                "form": "13F-HR",
                "filing_date": "2024-08-14",
                "fingerprint": "c-fp",
                "candidate_reason": "thirteenf_filing",
                "artifact_required": True,
            }
        ],
        "quarter_index_fingerprints": [["2024Q3", "q"]],
    }
    assert validate_strict_release_manifest(payload) == windows
    inventory = candidate_inventory_from_manifest(
        payload, ciks={9}, require_strict_agent_windows=True
    )
    assert inventory.candidates[0].accession_number == "new-13f"


def test_strict_release_rejects_out_of_window_candidate() -> None:
    watermark = date(2026, 7, 2)
    windows = agent_coverage_by_document_type(watermark)
    payload = {
        "coverage_start": index_floor_coverage_start(windows).isoformat(),
        "coverage_by_document_type": windows,
        "watermark": watermark.isoformat(),
        "fingerprint": "bad-fp",
        "candidates": [
            {
                "accession_number": "old-13f",
                "cik": 9,
                "form": "13F-HR",
                "filing_date": "2020-08-14",
                "fingerprint": "c-fp",
                "candidate_reason": "thirteenf_filing",
                "artifact_required": True,
            }
        ],
    }
    with pytest.raises(InventoryError, match="outside locked agent windows"):
        validate_strict_release_manifest(payload)


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


def test_ticket20_accepted_unresolved_bounded_threshold() -> None:
    """Release-Owner-accepted Item 5.02 unresolved exception (gate doctrine,
    2026-07-19): unresolved_accepted is terminal but bounded — PASS requires
    the count to match the enumerated accession list exactly and the rate to
    stay within the accepted threshold; both violations fail closed."""
    from edgar_warehouse.application.relationship_bulk_load import (
        build_required_relationship_bulk_load_evidence,
    )

    watermark = date(2026, 7, 2)
    windows = agent_coverage_by_document_type(watermark)
    common = dict(
        generation_id="run-1",
        inventory_fingerprint="fp",
        watermark=watermark,
        coverage_start=index_floor_coverage_start(windows),
        coverage_by_document_type=windows,
        ledger_fingerprint="ledger-fp",
        batch_ledger_count=1,
        require_attestations=False,
    )

    # Under threshold with exact enumeration: PASS, claim names the count.
    evidence = build_required_relationship_bulk_load_evidence(
        candidate_count=100,
        terminal_counts={"applicable_loaded": 95, "not_applicable": 3,
                         "unresolved_accepted": 2},
        accepted_unresolved_accessions=["acc-1", "acc-2"],
        item502_candidate_count=50,
        **common,
    )
    assert evidence["disposition"] == "PASS"
    assert evidence["accepted_unresolved"]["count"] == 2
    assert evidence["accepted_unresolved"]["accessions"] == ["acc-1", "acc-2"]
    assert "EXCEPT for 2 enumerated unresolved candidates" in evidence["pass_claim"]
    assert "not claimed complete" in evidence["pass_claim"]

    # Over threshold: fail closed (2/10 = 20% > 9.5%).
    with pytest.raises(InventoryError, match="exceeds bounded threshold"):
        build_required_relationship_bulk_load_evidence(
            candidate_count=100,
            terminal_counts={"applicable_loaded": 95, "not_applicable": 3,
                             "unresolved_accepted": 2},
            accepted_unresolved_accessions=["acc-1", "acc-2"],
            item502_candidate_count=10,
            **common,
        )

    # Count without enumeration: fail closed (nothing accepted silently).
    with pytest.raises(InventoryError, match="enumerated"):
        build_required_relationship_bulk_load_evidence(
            candidate_count=100,
            terminal_counts={"applicable_loaded": 95, "not_applicable": 3,
                             "unresolved_accepted": 2},
            accepted_unresolved_accessions=[],
            item502_candidate_count=50,
            **common,
        )

    # Zero accepted: claim keeps the plain (complete) Item 5.02 clause.
    clean = build_required_relationship_bulk_load_evidence(
        candidate_count=100,
        terminal_counts={"applicable_loaded": 97, "not_applicable": 3},
        **common,
    )
    assert "EXCEPT" not in clean["pass_claim"]
    assert "accepted_unresolved" not in clean


def test_release_mode_item502_unresolved_records_accepted_terminal_status() -> None:
    """fundamentals_ingest no longer hard-raises on an unresolved Item 5.02
    parse under release_mode; it records the bounded unresolved_accepted
    terminal outcome (threshold enforced later at evidence time)."""
    from unittest.mock import patch

    from edgar_warehouse.application.workflows.fundamentals_ingest import (
        run_bootstrap_fundamentals_per_filing,
    )

    class FakeSource:
        def fetch(self, sql, params=None):
            if "sec_company_filing" in sql:
                return [{
                    "accession_number": "acc-unres", "cik": 88000, "form": "8-K",
                    "filing_date": "2024-08-19", "items": "5.02",
                }]
            if "sec_filing_attachment" in sql:
                return [{"accession_number": "acc-unres", "is_primary": True,
                         "raw_object_id": "raw-1"}]
            if "sec_raw_object" in sql:
                return [{"raw_object_id": "raw-1", "storage_path": "mem://doc"}]
            return []

        def merge_earnings_releases(self, rows, run_id):
            return 0

        def merge_executive_records(self, rows, run_id):
            return 0

        def merge_employment_events(self, rows, run_id):
            return len(rows)

    db = FakeSource()
    content = (b"Item 5.02 Departure of Directors. The Board named the following "
               b"to committees and other matters were discussed at length.")
    with patch(
        "edgar_warehouse.infrastructure.object_storage.read_bytes",
        return_value=content,
    ):
        metrics = run_bootstrap_fundamentals_per_filing(
            cik_list=[88000],
            source=db,
            db=db,
            sync_run_id="run-1",
            release_mode=True,
            candidate_accessions={"acc-unres"},
        )
    outcomes = {row["accession_number"]: row for row in metrics["candidate_outcomes"]}
    assert outcomes["acc-unres"]["status"] in (
        "unresolved_accepted", "not_applicable"
    )
    # If the parser resolved it (not_applicable/applicable), that's fine too —
    # the invariant under test is: NO raise, and IF unresolved it must be
    # recorded as unresolved_accepted with the accession tracked.
    if outcomes["acc-unres"]["status"] == "unresolved_accepted":
        assert outcomes["acc-unres"]["reason"] == "item_502_unresolved_ambiguous_verb"
        assert "acc-unres" in metrics.get("unresolved_item502", [])


def test_insider_inventory_dedupes_and_excludes_corporates() -> None:
    """Ticket 21 slice 1: one observation per (owner, issuer) across filings,
    flags OR-merged, corporate owners excluded, nameless+cikless rows dropped."""
    from edgar_warehouse.application.relationship_bulk_load import insider_inventory

    class FakeSilver:
        def fetch(self, sql, params=None):
            assert "sec_ownership_reporting_owner" in sql
            assert params == [88000]
            return [
                {"owner_cik": 1111, "owner_name": "Jane Doe", "issuer_cik": 88000,
                 "is_director": 1, "is_officer": 0, "is_ten_percent_owner": 0},
                # same person+issuer from a later filing, officer flag now set
                {"owner_cik": 1111, "owner_name": "Jane Doe", "issuer_cik": 88000,
                 "is_director": 0, "is_officer": 1, "is_ten_percent_owner": 0},
                # corporate reporting owner — excluded
                {"owner_cik": 500, "owner_name": "Fund LP", "issuer_cik": 88000,
                 "is_director": 0, "is_officer": 0, "is_ten_percent_owner": 1},
                # name-only identity (no owner_cik)
                {"owner_cik": None, "owner_name": "Bob Roe", "issuer_cik": 88000,
                 "is_director": 0, "is_officer": 1, "is_ten_percent_owner": 0},
                # no identity at all — dropped
                {"owner_cik": None, "owner_name": " ", "issuer_cik": 88000,
                 "is_director": 1, "is_officer": 0, "is_ten_percent_owner": 0},
            ]

    inventory = insider_inventory(FakeSilver(), [88000], exclude_owner_ciks=[500])
    assert len(inventory) == 2
    jane = next(o for o in inventory if o.owner_cik == 1111)
    assert jane.is_director and jane.is_officer and not jane.is_ten_percent_owner
    bob = next(o for o in inventory if o.owner_cik is None)
    assert bob.owner_name == "Bob Roe"


def test_partition_insider_coverage_fail_closed_partition() -> None:
    """Ticket 21 slice 2: identified requires person AND issuer AND an
    IS_INSIDER version; each failure mode lands in unresolved with a reason."""
    from edgar_warehouse.application.relationship_bulk_load import (
        InsiderObservation, partition_insider_coverage,
    )

    inv = [
        InsiderObservation(1111, "Jane Doe", 88000, True, True, False),
        InsiderObservation(2222, "No Person", 88000, True, False, False),
        InsiderObservation(3333, "No Issuer", 77000, True, False, False),
        InsiderObservation(4444, "No Version", 88000, False, True, False),
    ]
    result = partition_insider_coverage(
        inv,
        resolve_person=lambda cik, name: None if cik == 2222 else f"p{cik}",
        resolve_issuer=lambda cik: None if cik == 77000 else f"c{cik}",
        has_insider_version=lambda p, c: p != "p4444",
    )
    assert result["insider_total"] == 4
    assert result["insider_identified"] == 1
    assert result["insider_unresolved"] == 3
    reasons = {r["owner_cik"]: r["reason"] for r in result["unresolved"]}
    assert reasons == {2222: "unresolved_person", 3333: "unresolved_issuer",
                       4444: "missing_is_insider_version"}


def test_evidence_insider_coverage_fail_closed_and_embedded() -> None:
    """Ticket 21 slice 3: when insider_coverage is provided, PASS requires
    zero unresolved insiders; the block is embedded in evidence on success."""
    from edgar_warehouse.application.relationship_bulk_load import (
        build_required_relationship_bulk_load_evidence,
    )

    watermark = date(2026, 7, 2)
    windows = agent_coverage_by_document_type(watermark)
    common = dict(
        generation_id="run-1",
        inventory_fingerprint="fp",
        watermark=watermark,
        coverage_start=index_floor_coverage_start(windows),
        coverage_by_document_type=windows,
        candidate_count=10,
        terminal_counts={"applicable_loaded": 10},
        ledger_fingerprint="ledger-fp",
        batch_ledger_count=1,
        require_attestations=False,
    )
    clean = build_required_relationship_bulk_load_evidence(
        insider_coverage={"insider_total": 5, "insider_identified": 5,
                          "insider_unresolved": 0, "unresolved": [],
                          "source": "sec_ownership_reporting_owner"},
        **common,
    )
    assert clean["insider_coverage"]["insider_identified"] == 5

    with pytest.raises(InventoryError, match="unresolved insiders"):
        build_required_relationship_bulk_load_evidence(
            insider_coverage={"insider_total": 5, "insider_identified": 4,
                              "insider_unresolved": 1,
                              "unresolved": [{"owner_cik": 1, "issuer_cik": 2,
                                              "reason": "unresolved_person"}]},
            **common,
        )

    # Omitted entirely: evidence has no insider block (pre-Ticket-21 shape).
    legacy = build_required_relationship_bulk_load_evidence(**common)
    assert "insider_coverage" not in legacy
