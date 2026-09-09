"""Regression guard for the legal_suffix seed-data drift found 2026-09-09.

edgar_warehouse/mdm/migrations/002_seed_data.sql is NOT executed by `mdm
migrate` -- the actually-executed seed logic is
edgar_warehouse.mdm.migrations.runtime._seed_normalization_rules. The two
had silently drifted (the SQL file had 8 legal_suffix rows the Python
function lacked) before this was discovered live against prod. This test
parses the SQL file's legal_suffix INSERT block and asserts every row it
declares also exists in what `mdm migrate` actually seeds, so a future
edit to only one side is caught here instead of drifting again.
"""
from __future__ import annotations

import re
from pathlib import Path

from tests.mdm.test_run_companies_concurrency import _seeded_sqlite_session

_SEED_SQL_PATH = (
    Path(__file__).resolve().parents[2]
    / "edgar_warehouse"
    / "mdm"
    / "migrations"
    / "002_seed_data.sql"
)


def _legal_suffix_rows_from_sql_file() -> set[str]:
    sql = _SEED_SQL_PATH.read_text(encoding="utf-8")
    return set(re.findall(r"\('legal_suffix',\s*'([^']+)'", sql))


def test_python_seed_covers_every_sql_file_legal_suffix_row() -> None:
    sql_tokens = _legal_suffix_rows_from_sql_file()
    assert sql_tokens, "expected to find legal_suffix rows in 002_seed_data.sql"

    session = _seeded_sqlite_session(static_pool=True)
    from edgar_warehouse.mdm.database import MdmNormalizationRule
    from sqlalchemy import select

    seeded_tokens = {
        row.input_value.lower()
        for row in session.execute(
            select(MdmNormalizationRule).where(
                MdmNormalizationRule.rule_type == "legal_suffix"
            )
        ).scalars()
    }

    missing = sql_tokens - seeded_tokens
    assert not missing, (
        f"legal_suffix tokens declared in 002_seed_data.sql (documentation "
        f"only, not executed) but missing from the actually-executed "
        f"_seed_normalization_rules: {sorted(missing)}"
    )
