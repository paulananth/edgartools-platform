"""run_bootstrap_entity_facts scores accounting flags in memory, per CIK
(silver-merge-engine-migration Ticket 03), replacing bootstrap_fundamentals'
post-run backfill_accounting_flags loop that read local DuckDB back.
"""

from __future__ import annotations

from unittest.mock import patch

from edgar_warehouse.application.workflows.fundamentals_ingest import run_bootstrap_entity_facts

_ACCESSION = "0000320193-24-000123"


def _fact(concept, value):
    return {
        "cik": 320193, "accession_number": _ACCESSION, "fiscal_year": 2024,
        "fiscal_period": "FY", "period_end": "2024-09-28", "period_start": "2023-10-01",
        "form_type": "10-K", "concept": concept, "value": value, "unit": "USD",
        "decimals": 0, "segment": "consolidated", "parser_version": "1",
    }


_PARSED = {
    "sec_financial_fact": [
        _fact("Revenues", 391035000000.0),
        _fact("NetIncomeLoss", 93736000000.0),
        _fact("Assets", 364980000000.0),
        _fact("Liabilities", 308030000000.0),
        _fact("StockholdersEquity", 56950000000.0),
    ],
    "sec_accounting_flag": [
        {
            "cik": 320193, "accession_number": _ACCESSION, "fiscal_year": 2024,
            "period_end": "2024-09-28", "form_type": "10-K", "auditor_name": "EY",
            "beneish_m_score": None, "altman_z_score": None, "piotroski_f_score": None,
            "parser_version": "1",
        }
    ],
}


class _Db:
    def __init__(self):
        self.calls: list[tuple[str, list[dict]]] = []

    def fetch(self, query, params=None):
        return []

    def merge_financial_facts(self, rows, sync_run_id):
        self.calls.append(("facts", rows))
        return len(rows)

    def merge_financial_derived(self, rows, sync_run_id):
        self.calls.append(("derived", rows))
        return len(rows)

    def merge_accounting_flags(self, rows, sync_run_id):
        self.calls.append(("flags", rows))
        return len(rows)

    def mark_entity_facts_refreshed(self, cik):
        self.calls.append(("marker", [{"cik": cik}]))


def _run(db, **patches):
    with patch(
        "edgar_warehouse.infrastructure.edgartools_sec_gateway.fetch_companyfacts_json",
        return_value={"cik": 320193},
    ), patch(
        "edgar_warehouse.parsers.financials.parse_entity_facts", return_value=_PARSED
    ):
        return run_bootstrap_entity_facts(
            cik_list=[320193], db=db, identity="Test test@example.com",
            sync_run_id="run-1", force=True, **patches,
        )


def test_flags_are_scored_from_the_same_ciks_derived_rows_before_being_written() -> None:
    db = _Db()

    metrics = _run(db)

    order = [name for name, _ in db.calls]
    assert order == ["facts", "derived", "flags", "marker"]
    flags = dict(db.calls)["flags"]
    assert flags[0]["altman_z_score"] is not None
    assert flags[0]["piotroski_f_score"] is not None
    assert flags[0]["auditor_name"] == "EY"
    assert metrics["accounting_flags_updated"] == 1
    assert metrics["rows_accounting_flag"] == 1


def test_a_scoring_failure_still_writes_the_unscored_flags() -> None:
    db = _Db()

    with patch(
        "edgar_warehouse.parsers.accounting_flags.score_accounting_flags",
        side_effect=RuntimeError("boom"),
    ), patch("edgar_warehouse.application.workflows.fundamentals_ingest._emit") as emit:
        metrics = _run(db)

    flags = dict(db.calls)["flags"]
    assert flags == _PARSED["sec_accounting_flag"]
    assert metrics["accounting_flags_updated"] == 0
    assert metrics["ciks_processed"] == 1
    assert any(c.args[0] == "accounting_flags_backfill_error" for c in emit.call_args_list)
