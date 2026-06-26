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


if __name__ == "__main__":
    unittest.main()
