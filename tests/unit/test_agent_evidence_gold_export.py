"""Ticket 08: issuer neighborhood evidence tables in gold export registry."""

from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from edgar_warehouse.infrastructure.run_manifest_builder import SNOWFLAKE_EXPORT_TABLES
from edgar_warehouse.serving.source_dimensional_export import (
    _build_sec_auditor_report_evidence,
    _build_sec_employment_event,
    _build_sec_subsidiary_evidence,
)
from edgar_warehouse.serving.targets.snowflake import write_gold_to_serving_export
from tests.unit._fake_snowflake import FakeSnowflakeConnectionSettings

_SUBSIDIARY_COLUMNS = [
    "accession_number", "registrant_cik", "document_name", "document_type",
    "row_ordinal", "legal_name", "jurisdiction", "parent_scope",
    "immediate_parent_known", "effective_date", "row_locator",
    "source_sha256", "parser_version",
]
_AUDITOR_COLUMNS = [
    "accession_number", "registrant_cik", "form_type", "document_name",
    "audited_period_end", "report_date", "principal_firm_name",
    "principal_firm_location", "pcaob_firm_id", "evidence_source",
    "raw_locator", "source_sha256", "evidence_fingerprint",
    "form_ap_filing_id", "original_form_ap_filing_id", "latest_amendment",
    "parser_version",
]
_EMPLOYMENT_COLUMNS = [
    "accession_number", "event_index", "cik", "event_type", "person_name",
    "exec_role", "previous_role", "compensation_amount", "effective_date",
    "parser_version",
]


def _populated_table_data() -> dict[str, tuple[list[str], list[tuple]]]:
    return {
        "SEC_SUBSIDIARY_EVIDENCE": (
            _SUBSIDIARY_COLUMNS,
            [
                (
                    "0001", 320193, "ex21.htm", "EX-21", 1, "SubCo", "DE",
                    "registrant_disclosed", False, date(2024, 1, 1), "r1",
                    "abc", "v1",
                )
            ],
        ),
        "SEC_AUDITOR_REPORT_EVIDENCE": (
            _AUDITOR_COLUMNS,
            [
                (
                    "0001", 320193, "10-K", "a.htm", date(2023, 12, 31),
                    date(2024, 2, 1), "EY", "NY", "42", "sec_ixbrl", "loc",
                    "sha", "fp1", None, None, True, "v1",
                )
            ],
        ),
        "SEC_EMPLOYMENT_EVENT": (
            _EMPLOYMENT_COLUMNS,
            [
                (
                    "0001", 1, 320193, "appointed", "Jane Doe", "CEO", None,
                    None, date(2024, 3, 1), "v1",
                )
            ],
        ),
    }


def _empty_table_data() -> dict[str, tuple[list[str], list[tuple]]]:
    return {
        "SEC_SUBSIDIARY_EVIDENCE": (_SUBSIDIARY_COLUMNS, []),
        "SEC_AUDITOR_REPORT_EVIDENCE": (_AUDITOR_COLUMNS, []),
        "SEC_EMPLOYMENT_EVENT": (_EMPLOYMENT_COLUMNS, []),
    }


class AgentEvidenceExportTests(unittest.TestCase):
    def test_export_registry_includes_evidence_tables(self) -> None:
        for name in (
            "SEC_SUBSIDIARY_EVIDENCE",
            "SEC_AUDITOR_REPORT_EVIDENCE",
            "SEC_EMPLOYMENT_EVENT",
        ):
            self.assertIn(name, SNOWFLAKE_EXPORT_TABLES)

    def test_builders_export_rows(self) -> None:
        with patch(
            "edgar_warehouse.mdm.export.silver_connection_settings",
            return_value=FakeSnowflakeConnectionSettings(_populated_table_data()),
        ):
            self.assertEqual(_build_sec_subsidiary_evidence().num_rows, 1)
            self.assertEqual(_build_sec_auditor_report_evidence().num_rows, 1)
            self.assertEqual(_build_sec_employment_event().num_rows, 1)

    def test_write_serving_export_includes_evidence_paths(self) -> None:
        with patch(
            "edgar_warehouse.mdm.export.silver_connection_settings",
            return_value=FakeSnowflakeConnectionSettings(_empty_table_data()),
        ):
            tables = {
                "sec_subsidiary_evidence": _build_sec_subsidiary_evidence(),
                "sec_auditor_report_evidence": _build_sec_auditor_report_evidence(),
                "sec_employment_event": _build_sec_employment_event(),
            }

        class _Root:
            def __init__(self, base: Path):
                self.base = base
                self.written: list[str] = []

            def write_bytes(self, relative_path: str, payload: bytes) -> str:
                path = self.base / relative_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(payload)
                self.written.append(relative_path)
                return str(path)

        with tempfile.TemporaryDirectory() as tmp:
            root = _Root(Path(tmp))
            counts = write_gold_to_serving_export(
                tables, root, run_id="run1", business_date="2024-01-01"
            )
            self.assertIn("sec_subsidiary_evidence", counts)
            self.assertIn("sec_auditor_report_evidence", counts)
            self.assertIn("sec_employment_event", counts)
            joined = " ".join(root.written)
            self.assertIn("sec_subsidiary_evidence", joined)
            self.assertIn("sec_auditor_report_evidence", joined)
            self.assertIn("sec_employment_event", joined)


if __name__ == "__main__":
    unittest.main()
