"""Unit tests for CompanyResolver's parent-CIK lookup.

See TODOS.md "parent_company_entity_id_always_none" — no upstream source
ever populates parent_company_cik/parent_cik/ultimate_parent_cik on the
silver sec_company row, so this lookup always returns None today. That gap
should be observable (a warning) rather than silent.
"""
from __future__ import annotations

import logging

from edgar_warehouse.mdm.resolvers.base import ResolverContext
from edgar_warehouse.mdm.resolvers.company import CompanyResolver


def test_warns_once_per_run_when_parent_cik_source_missing(caplog) -> None:
    ctx = ResolverContext(session=None, engine=None, silver=None, run_id="run-1")
    resolver = CompanyResolver()

    with caplog.at_level(logging.WARNING):
        result_1 = resolver._parent_company_entity_id(ctx, {"cik": 1})
        result_2 = resolver._parent_company_entity_id(ctx, {"cik": 2})

    assert result_1 is None
    assert result_2 is None
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1, "should warn once per run, not once per row"
    assert "parent_company_cik" in warnings[0].message or "parent CIK" in warnings[0].message


def test_no_warning_when_parent_cik_present() -> None:
    ctx = ResolverContext(session=None, engine=None, silver=None, run_id="run-2")
    resolver = CompanyResolver()

    logger = logging.getLogger("edgar_warehouse.mdm.resolvers.company")
    records: list[logging.LogRecord] = []
    handler = logging.Handler()
    handler.emit = records.append  # type: ignore[assignment]
    logger.addHandler(handler)
    try:
        # parent_cik present but not resolvable to an existing entity still
        # short-circuits before touching ctx.session (None here), proving no
        # warning fires on this path.
        result = resolver._parent_company_entity_id(ctx, {"cik": 1, "parent_cik": ""})
    finally:
        logger.removeHandler(handler)

    assert result is None
    assert not any(r.levelno == logging.WARNING for r in records)
