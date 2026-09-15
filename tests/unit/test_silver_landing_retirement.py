"""Ticket 35: retirement records drop a key from the silver collapse.

The `silver_not_retired` dbt macro is an anti-join against
SILVER_LANDING_RETIREMENT: the latest retirement event per business key wins,
and a later landing row (higher parse_sequence) reinstates the key. Its
semantics used to be proven by running a copy of the macro SQL in DuckDB;
that engine left the repo (silver-merge-engine-migration Ticket 17) and no
local engine runs Snowflake-dialect SQL, so these guards hold the macro's
load-bearing clauses as text. A Snowflake-backed dbt test is the only way to
execute it now.
"""

from __future__ import annotations

import re
from pathlib import Path

_DBT_ROOT = Path("infra/snowflake/dbt/edgartools_gold")
_MACRO = _DBT_ROOT / "macros" / "silver_not_retired.sql"


def _normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text).lower()


def test_macro_keeps_only_the_latest_retirement_event_per_key() -> None:
    text = _normalized(_MACRO.read_text())
    assert "partition by business_key order by parse_sequence desc" in text
    assert "retired.rn = 1" in text


def test_macro_retires_only_rows_older_than_the_retirement_event() -> None:
    """A later landing row reinstates a retired key: the comparison must be a
    strict "retirement is newer than the row", never >= or an unconditional
    match on the key."""
    text = _normalized(_MACRO.read_text())
    assert "not exists (" in text
    assert "retired.business_key = {{ business_key_expr }}" in text
    assert "retired.parse_sequence > {{ parse_sequence_expr }}" in text


def test_macro_scopes_retirements_to_its_target_table() -> None:
    text = _normalized(_MACRO.read_text())
    assert "upper(target_table) = upper('{{ target_table }}')" in text


def test_silver_model_config_keeps_six_hour_target_lag() -> None:
    """Ticket 35: the completion barrier layers on top of this lag, not over it."""

    text = (_DBT_ROOT / "macros" / "silver_model_config.sql").read_text()
    assert "target_lag='6 hours'" in text
