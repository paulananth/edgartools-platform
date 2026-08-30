"""Item 5.02 integration into Branch A configured-forms parse path."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from edgar_warehouse.application import warehouse_orchestrator as orch


class TestParserMetadataItem502:
    def test_item_502_family_when_items_declare_502(self):
        name, version, family = orch._parser_metadata("8-K", items="5.02")
        assert family == "item_502"
        assert name == "item_502"
        assert version

    def test_ambiguous_empty_items_is_item_502_family(self):
        _, _, family = orch._parser_metadata("8-K/A", items="")
        assert family == "item_502"

    def test_unrelated_8k_is_generic(self):
        _, _, family = orch._parser_metadata("8-K", items="2.02")
        assert family == "generic"


class TestParseItem502Accession:
    def test_merges_employment_events(self, monkeypatch):
        filing = {
            "accession_number": "0001",
            "cik": 320193,
            "form": "8-K",
            "items": "5.02",
            "filing_date": date(2025, 6, 1),
        }
        db = MagicMock()
        db.merge_employment_events.return_value = 1

        event = SimpleNamespace(
            accession_number="0001",
            cik=320193,
            event_type="appointment",
            person_name="Jane Doe",
            role="CEO",
            previous_role=None,
            compensation_amount=None,
            effective_date=date(2025, 6, 1),
        )
        result = SimpleNamespace(
            applicability="applicable",
            reason_code="named_employment_event",
            events=(event,),
        )

        monkeypatch.setattr(
            orch, "_read_primary_artifact_bytes", lambda db, acc: b"Item 5.02 body"
        )

        import edgar_warehouse.parsers.item_502 as item_502_mod

        monkeypatch.setattr(item_502_mod, "parse_item_502", lambda **kwargs: result)
        monkeypatch.setattr(item_502_mod, "PARSER_VERSION", "test-v1")

        rows = orch._parse_item_502_accession(
            db=db,
            filing=filing,
            accession_number="0001",
            sync_run_id="run-1",
        )
        assert rows == 1
        merged = db.merge_employment_events.call_args[0][0]
        assert merged[0]["person_name"] == "Jane Doe"
        assert merged[0]["event_type"] == "appointment"
        assert merged[0]["parser_version"] == "test-v1"

    def test_run_parse_pipeline_dispatches_item_502(self, monkeypatch):
        filing = {
            "accession_number": "0001",
            "cik": 320193,
            "form": "8-K",
            "items": "5.02",
            "filing_date": date(2025, 6, 1),
        }
        db = MagicMock()
        db.get_filing.return_value = filing
        db.start_parse_run.return_value = None
        db.complete_parse_run.return_value = None

        monkeypatch.setattr(
            orch,
            "_parse_item_502_accession",
            lambda **kwargs: 2,
        )
        rows = orch._run_parse_pipeline(
            db=db,
            bookkeeping=db,
            accession_number="0001",
            sync_run_id="run-1",
        )
        assert rows == 2
        assert db.complete_parse_run.call_args.kwargs["status"] == "succeeded"
        assert db.complete_parse_run.call_args.kwargs["rows_written"] == 2
