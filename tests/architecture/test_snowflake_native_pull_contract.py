from __future__ import annotations

import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
NATIVE_PULL_MAIN = REPO_ROOT / "infra" / "terraform" / "snowflake" / "modules" / "native_pull" / "main.tf"
NATIVE_PULL_PROC = (
    REPO_ROOT
    / "infra"
    / "terraform"
    / "snowflake"
    / "modules"
    / "native_pull"
    / "sql"
    / "source_load_procedure.sql"
)
BOOTSTRAP_LOAD_PROC = REPO_ROOT / "infra" / "snowflake" / "sql" / "bootstrap" / "03_source_load_wrapper.sql"
SOURCE_STAGE_SQL = REPO_ROOT / "infra" / "snowflake" / "sql" / "bootstrap" / "01_source_stage.sql"
MDM_EXPORT_TARGETS_SQL = (
    REPO_ROOT / "infra" / "snowflake" / "sql" / "bootstrap" / "07_mdm_export_targets.sql"
)


class SnowflakeNativePullContractTests(unittest.TestCase):
    def test_financial_fact_table_contains_all_loader_merge_keys(self) -> None:
        main_tf = NATIVE_PULL_MAIN.read_text(encoding="utf-8")
        block_match = re.search(
            r"SEC_FINANCIAL_FACT = \{(?P<block>.*?)\n    SEC_THIRTEENF_HOLDING = \{",
            main_tf,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(block_match)
        block = block_match.group("block")

        for column in (
            "CIK",
            "ACCESSION_NUMBER",
            "CONCEPT",
            "FISCAL_PERIOD",
            "SEGMENT",
            "PERIOD_END",
            "PERIOD_START",
        ):
            self.assertIn(f'name = "{column}"', block)

        self.assertRegex(
            block,
            r'name = "PERIOD_START", type = "DATE", nullable = false',
        )

    def test_financial_fact_merge_keys_match_bootstrap_and_terraform_loader(self) -> None:
        expected = (
            '["CIK", "ACCESSION_NUMBER", "CONCEPT", "FISCAL_PERIOD", '
            '"SEGMENT", "PERIOD_END", "PERIOD_START"]'
        )

        self.assertIn(
            f'["SEC_FINANCIAL_FACT", {expected}]',
            NATIVE_PULL_PROC.read_text(encoding="utf-8"),
        )
        self.assertIn(
            f'["SEC_FINANCIAL_FACT", {expected}]',
            BOOTSTRAP_LOAD_PROC.read_text(encoding="utf-8"),
        )

    def test_financial_fact_period_start_migration_uses_live_safe_snowflake_form(self) -> None:
        source_stage = SOURCE_STAGE_SQL.read_text(encoding="utf-8")

        self.assertIn("ALTER TABLE SEC_FINANCIAL_FACT ADD COLUMN IF NOT EXISTS period_start DATE;", source_stage)
        self.assertIn("SET period_start = DATE '0001-01-01'", source_stage)
        self.assertIn("ALTER TABLE SEC_FINANCIAL_FACT ALTER COLUMN period_start SET NOT NULL;", source_stage)
        self.assertNotIn(
            "ALTER TABLE SEC_FINANCIAL_FACT ADD COLUMN IF NOT EXISTS period_start DATE NOT NULL DEFAULT",
            source_stage,
        )

    def test_mdm_fund_export_target_contains_private_fund_id(self) -> None:
        export_targets = MDM_EXPORT_TARGETS_SQL.read_text(encoding="utf-8")

        self.assertRegex(
            export_targets,
            r"(?s)CREATE TABLE IF NOT EXISTS MDM_FUND \(.*?private_fund_id\s+VARCHAR",
        )
        self.assertIn(
            "ALTER TABLE MDM_FUND ADD COLUMN IF NOT EXISTS private_fund_id VARCHAR;",
            export_targets,
        )


if __name__ == "__main__":
    unittest.main()
