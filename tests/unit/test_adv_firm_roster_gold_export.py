"""Ticket 03: Firm Roster crosscheck passthrough tables in gold export registry."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import duckdb

from edgar_warehouse.infrastructure.run_manifest_builder import SNOWFLAKE_EXPORT_TABLES
from edgar_warehouse.serving.gold_models import (
    _build_sec_adv_firm_roster,
    _build_sec_adv_private_fund_passthrough,
)
from edgar_warehouse.serving.targets.snowflake import write_gold_to_serving_export


class AdvFirmRosterExportTests(unittest.TestCase):
    def test_export_registry_includes_firm_roster_tables(self) -> None:
        for name in ("SEC_ADV_FIRM_ROSTER", "SEC_ADV_PRIVATE_FUND"):
            self.assertIn(name, SNOWFLAKE_EXPORT_TABLES)

    def test_builders_export_rows(self) -> None:
        conn = duckdb.connect(":memory:")
        conn.execute(
            """
            CREATE TABLE sec_adv_firm_roster (
                adviser_crd_number TEXT, dataset_period TEXT,
                private_funds_reported BOOLEAN, private_fund_count_7b1 BIGINT,
                any_hedge_funds BOOLEAN, hedge_fund_count BIGINT,
                any_pe_funds BOOLEAN, pe_fund_count BIGINT,
                total_gross_assets_private_funds DECIMAL(28,2),
                private_fund_count_7b2 BIGINT, source_sha256 TEXT, parser_version TEXT
            );
            INSERT INTO sec_adv_firm_roster VALUES
              ('1588', '2026-07', true, 3, true, 3, false, NULL, 709905606.00, 0,
               'abc123', 'firm_roster_v1');
            CREATE TABLE sec_adv_private_fund (
                accession_number TEXT, fund_index BIGINT, filing_id TEXT,
                adviser_crd_number TEXT, private_fund_id TEXT, reference_id TEXT,
                schedule_section TEXT, reporting_role TEXT, filing_action TEXT,
                fund_name TEXT, fund_type TEXT, jurisdiction TEXT,
                aum_amount DECIMAL(28,2), effective_date DATE,
                source_dataset_period TEXT, source_sha256 TEXT, parser_version TEXT
            );
            INSERT INTO sec_adv_private_fund VALUES
              ('iapd-adv:2115188', 1, '2115188', '129052', '805-123', '518607',
               '7B1', 'detailed_reporter', 'current_compilation', 'ALPHA FUND',
               'Private Equity Fund', 'Delaware / United States', 321687148.00,
               DATE '2026-06-24', '2026-06', 'abc123', 'iapd_bulk_v1');
            """
        )
        self.assertEqual(_build_sec_adv_firm_roster(conn).num_rows, 1)
        self.assertEqual(_build_sec_adv_private_fund_passthrough(conn).num_rows, 1)

    def test_write_serving_export_includes_firm_roster_paths(self) -> None:
        conn = duckdb.connect(":memory:")
        conn.execute(
            """
            CREATE TABLE sec_adv_firm_roster (
                adviser_crd_number TEXT, dataset_period TEXT,
                private_funds_reported BOOLEAN, private_fund_count_7b1 BIGINT,
                any_hedge_funds BOOLEAN, hedge_fund_count BIGINT,
                any_pe_funds BOOLEAN, pe_fund_count BIGINT,
                total_gross_assets_private_funds DECIMAL(28,2),
                private_fund_count_7b2 BIGINT, source_sha256 TEXT, parser_version TEXT
            );
            CREATE TABLE sec_adv_private_fund (
                accession_number TEXT, fund_index BIGINT, filing_id TEXT,
                adviser_crd_number TEXT, private_fund_id TEXT, reference_id TEXT,
                schedule_section TEXT, reporting_role TEXT, filing_action TEXT,
                fund_name TEXT, fund_type TEXT, jurisdiction TEXT,
                aum_amount DECIMAL(28,2), effective_date DATE,
                source_dataset_period TEXT, source_sha256 TEXT, parser_version TEXT
            );
            """
        )
        tables = {
            "sec_adv_firm_roster": _build_sec_adv_firm_roster(conn),
            "sec_adv_private_fund": _build_sec_adv_private_fund_passthrough(conn),
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
            self.assertIn("sec_adv_firm_roster", counts)
            self.assertIn("sec_adv_private_fund", counts)
            joined = " ".join(root.written)
            self.assertIn("sec_adv_firm_roster", joined)
            self.assertIn("sec_adv_private_fund", joined)


if __name__ == "__main__":
    unittest.main()
