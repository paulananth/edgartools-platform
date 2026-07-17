"""Ticket 08: issuer neighborhood evidence tables in gold export registry."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import duckdb

from edgar_warehouse.infrastructure.run_manifest_builder import SNOWFLAKE_EXPORT_TABLES
from edgar_warehouse.serving.gold_models import (
    _build_sec_auditor_report_evidence,
    _build_sec_employment_event,
    _build_sec_subsidiary_evidence,
)
from edgar_warehouse.serving.targets.snowflake import write_gold_to_serving_export


class AgentEvidenceExportTests(unittest.TestCase):
    def test_export_registry_includes_evidence_tables(self) -> None:
        for name in (
            "SEC_SUBSIDIARY_EVIDENCE",
            "SEC_AUDITOR_REPORT_EVIDENCE",
            "SEC_EMPLOYMENT_EVENT",
        ):
            self.assertIn(name, SNOWFLAKE_EXPORT_TABLES)

    def test_builders_export_rows(self) -> None:
        conn = duckdb.connect(":memory:")
        conn.execute(
            """
            CREATE TABLE sec_subsidiary_evidence (
                accession_number TEXT, registrant_cik BIGINT, document_name TEXT,
                document_type TEXT, row_ordinal INTEGER, legal_name TEXT,
                jurisdiction TEXT, parent_scope TEXT, immediate_parent_known BOOLEAN,
                effective_date DATE, row_locator TEXT, source_sha256 TEXT, parser_version TEXT
            );
            INSERT INTO sec_subsidiary_evidence VALUES
              ('0001', 320193, 'ex21.htm', 'EX-21', 1, 'SubCo', 'DE',
               'registrant_disclosed', false, DATE '2024-01-01', 'r1', 'abc', 'v1');
            CREATE TABLE sec_auditor_report_evidence (
                accession_number TEXT, registrant_cik BIGINT, form_type TEXT,
                document_name TEXT, audited_period_end DATE, report_date DATE,
                principal_firm_name TEXT, principal_firm_location TEXT, pcaob_firm_id TEXT,
                evidence_source TEXT, raw_locator TEXT, source_sha256 TEXT,
                evidence_fingerprint TEXT, form_ap_filing_id TEXT,
                original_form_ap_filing_id TEXT, latest_amendment BOOLEAN, parser_version TEXT
            );
            INSERT INTO sec_auditor_report_evidence VALUES
              ('0001', 320193, '10-K', 'a.htm', DATE '2023-12-31', DATE '2024-02-01',
               'EY', 'NY', '42', 'sec_ixbrl', 'loc', 'sha', 'fp1', NULL, NULL, true, 'v1');
            CREATE TABLE sec_employment_event (
                accession_number TEXT, event_index BIGINT, cik BIGINT, event_type TEXT,
                person_name TEXT, exec_role TEXT, previous_role TEXT,
                compensation_amount DOUBLE, effective_date DATE, parser_version TEXT
            );
            INSERT INTO sec_employment_event VALUES
              ('0001', 1, 320193, 'appointed', 'Jane Doe', 'CEO', NULL, NULL,
               DATE '2024-03-01', 'v1');
            """
        )
        self.assertEqual(_build_sec_subsidiary_evidence(conn).num_rows, 1)
        self.assertEqual(_build_sec_auditor_report_evidence(conn).num_rows, 1)
        self.assertEqual(_build_sec_employment_event(conn).num_rows, 1)

    def test_write_serving_export_includes_evidence_paths(self) -> None:
        conn = duckdb.connect(":memory:")
        conn.execute(
            """
            CREATE TABLE sec_subsidiary_evidence (
                accession_number TEXT, registrant_cik BIGINT, document_name TEXT,
                document_type TEXT, row_ordinal INTEGER, legal_name TEXT,
                jurisdiction TEXT, parent_scope TEXT, immediate_parent_known BOOLEAN,
                effective_date DATE, row_locator TEXT, source_sha256 TEXT, parser_version TEXT
            );
            CREATE TABLE sec_auditor_report_evidence (
                accession_number TEXT, registrant_cik BIGINT, form_type TEXT,
                document_name TEXT, audited_period_end DATE, report_date DATE,
                principal_firm_name TEXT, principal_firm_location TEXT, pcaob_firm_id TEXT,
                evidence_source TEXT, raw_locator TEXT, source_sha256 TEXT,
                evidence_fingerprint TEXT, form_ap_filing_id TEXT,
                original_form_ap_filing_id TEXT, latest_amendment BOOLEAN, parser_version TEXT
            );
            CREATE TABLE sec_employment_event (
                accession_number TEXT, event_index BIGINT, cik BIGINT, event_type TEXT,
                person_name TEXT, exec_role TEXT, previous_role TEXT,
                compensation_amount DOUBLE, effective_date DATE, parser_version TEXT
            );
            """
        )
        tables = {
            "sec_subsidiary_evidence": _build_sec_subsidiary_evidence(conn),
            "sec_auditor_report_evidence": _build_sec_auditor_report_evidence(conn),
            "sec_employment_event": _build_sec_employment_event(conn),
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
