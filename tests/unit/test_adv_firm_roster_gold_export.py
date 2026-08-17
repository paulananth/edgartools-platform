"""Ticket 03: Firm Roster crosscheck passthrough tables in gold export registry."""

from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from edgar_warehouse.infrastructure.run_manifest_builder import SNOWFLAKE_EXPORT_TABLES
from edgar_warehouse.serving.gold_models import (
    _build_sec_adv_firm_roster,
    _build_sec_adv_private_fund_passthrough,
)
from edgar_warehouse.serving.targets.snowflake import write_gold_to_serving_export
from tests.unit._fake_snowflake import FakeSnowflakeConnectionSettings

_FIRM_ROSTER_COLUMNS = [
    "adviser_crd_number", "dataset_period", "private_funds_reported",
    "private_fund_count_7b1", "any_hedge_funds", "hedge_fund_count",
    "any_pe_funds", "pe_fund_count", "total_gross_assets_private_funds",
    "private_fund_count_7b2", "source_sha256", "parser_version",
]
_PRIVATE_FUND_COLUMNS = [
    "accession_number", "fund_index", "filing_id", "adviser_crd_number",
    "private_fund_id", "reference_id", "schedule_section", "reporting_role",
    "filing_action", "fund_name", "fund_type", "jurisdiction", "aum_amount",
    "effective_date", "source_dataset_period", "source_sha256",
    "parser_version",
]


def _populated_table_data() -> dict[str, tuple[list[str], list[tuple]]]:
    return {
        "SEC_ADV_FIRM_ROSTER": (
            _FIRM_ROSTER_COLUMNS,
            [
                (
                    "1588", "2026-07", True, 3, True, 3, False, None,
                    709905606.00, 0, "abc123", "firm_roster_v1",
                )
            ],
        ),
        "SEC_ADV_PRIVATE_FUND": (
            _PRIVATE_FUND_COLUMNS,
            [
                (
                    "iapd-adv:2115188", 1, "2115188", "129052", "805-123",
                    "518607", "7B1", "detailed_reporter",
                    "current_compilation", "ALPHA FUND", "Private Equity Fund",
                    "Delaware / United States", 321687148.00,
                    date(2026, 6, 24), "2026-06", "abc123", "iapd_bulk_v1",
                )
            ],
        ),
    }


def _empty_table_data() -> dict[str, tuple[list[str], list[tuple]]]:
    return {
        "SEC_ADV_FIRM_ROSTER": (_FIRM_ROSTER_COLUMNS, []),
        "SEC_ADV_PRIVATE_FUND": (_PRIVATE_FUND_COLUMNS, []),
    }


class AdvFirmRosterExportTests(unittest.TestCase):
    def test_export_registry_includes_firm_roster_tables(self) -> None:
        for name in ("SEC_ADV_FIRM_ROSTER", "SEC_ADV_PRIVATE_FUND"):
            self.assertIn(name, SNOWFLAKE_EXPORT_TABLES)

    def test_builders_export_rows(self) -> None:
        with patch(
            "edgar_warehouse.mdm.export.silver_connection_settings",
            return_value=FakeSnowflakeConnectionSettings(_populated_table_data()),
        ):
            self.assertEqual(_build_sec_adv_firm_roster().num_rows, 1)
            self.assertEqual(_build_sec_adv_private_fund_passthrough().num_rows, 1)

    def test_write_serving_export_includes_firm_roster_paths(self) -> None:
        with patch(
            "edgar_warehouse.mdm.export.silver_connection_settings",
            return_value=FakeSnowflakeConnectionSettings(_empty_table_data()),
        ):
            tables = {
                "sec_adv_firm_roster": _build_sec_adv_firm_roster(),
                "sec_adv_private_fund": _build_sec_adv_private_fund_passthrough(),
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
