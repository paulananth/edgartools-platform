"""Regression test for release-readiness ticket 85: gold_models.py's
regexp_replace SQL patterns ('\\s+') were embedded in plain (non-raw)
Python string literals, triggering an "invalid escape sequence '\\s'"
warning at compile time -- forward-compatibility noise today, a hard
SyntaxError in a future Python version. Fixed by making both
conn.execute(...) SQL blocks raw strings.

Compiles the source text directly (rather than importing the module) so
the check is independent of any cached .pyc bytecode -- an import-based
check could spuriously pass against a stale cache compiled before a
regression was reintroduced, since this warning is only emitted during
actual compilation, not stored in bytecode.

The warning's category changed across Python versions (DeprecationWarning
through 3.11, SyntaxWarning from 3.12 -- confirmed live: this repo's local
.venv is 3.11, the prod Docker image is 3.12), so this matches on message
text rather than a single hardcoded category to stay correct on either."""
from __future__ import annotations

import warnings
from pathlib import Path

_GOLD_MODELS_PATH = (
    Path(__file__).resolve().parents[2]
    / "edgar_warehouse"
    / "serving"
    / "gold_models.py"
)


def test_gold_models_source_compiles_without_invalid_escape_warnings() -> None:
    source = _GOLD_MODELS_PATH.read_text(encoding="utf-8")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        compile(source, str(_GOLD_MODELS_PATH), "exec")
    escape_warnings = [w for w in caught if "invalid escape sequence" in str(w.message)]
    assert escape_warnings == []
