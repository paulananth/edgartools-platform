"""Each MDM function that looks up a list of keys plans with its keys.

Profiling ticket 07, tuning (operator, 2026-10-09: "yes, add the test and the
rule"). PL/pgSQL may reuse a generic plan after five calls. For a lookup
against a list of keys held in a variable (`= ANY(keys)`, `&& keys`,
`?| keys`, `@> keys`, `<@ keys`) a generic plan cannot hash the list, so every
row is compared with every key and each save gets slower as the store grows.
Such a function carries `SET plan_cache_mode = force_custom_plan`. No other
function does: per-row statements would then plan again on every call, which
measured twice as slow (migration 011).

The rule reads the installed functions, so a later migration that adds such a
lookup, or replaces a function and drops its setting, fails here.
"""

from __future__ import annotations

import re

from sqlalchemy import text

from edgar_warehouse.mdm.clean.store import migrate
from tests.integration.test_clean_mdm_postgres import database, postgres  # noqa: F401

SETTING = "plan_cache_mode=force_custom_plan"
SNAPSHOT = "mdm.match_proposal_snapshot(jsonb)"


def key_lists(arguments: str, source: str) -> set[str]:
    """The array variables (arguments or DECLAREd) a function body looks up
    rows against."""
    declared = re.search(r"\bDECLARE\b(.*?)\bBEGIN\b", source, re.S | re.I)
    names = set(re.findall(r"\b(\w+)\s+[\w.%]+\[\]", arguments))
    names |= set(re.findall(r"\b(\w+)\s+[\w.%]+\[\]", declared.group(1) if declared else ""))
    return {
        name for name in names
        if re.search(rf"(=\s*ANY\s*\(\s*{name}\s*\)|(&&|\?\||@>|<@)\s*{name}\b)", source, re.I)
    }


def plpgsql_functions(conn) -> list[tuple[str, set[str], bool]]:
    return [
        (signature, key_lists(arguments, source), SETTING in (config or []))
        for signature, arguments, source, config in conn.execute(text("""
            SELECT p.oid::regprocedure::text, pg_get_function_arguments(p.oid), p.prosrc, p.proconfig
            FROM pg_proc p JOIN pg_language l ON l.oid = p.prolang
            WHERE p.pronamespace = 'mdm'::regnamespace AND l.lanname = 'plpgsql'
            ORDER BY 1"""))
    ]


def test_key_lists_finds_lookups_against_array_variables():
    body = "DECLARE keys text[]; n integer; BEGIN SELECT 1 FROM t WHERE a = ANY(keys) OR b && sources; END"
    assert key_lists("sources text[]", body) == {"keys", "sources"}
    assert key_lists("", "DECLARE ordering text[]; BEGIN ordering := ARRAY['a']; END") == set()


def test_only_functions_that_look_up_key_lists_plan_with_their_keys(database):
    with database.admin.connect() as conn:
        functions = plpgsql_functions(conn)
    assert functions
    wrong = [(name, sorted(lists), has) for name, lists, has in functions if bool(lists) != has]
    assert wrong == []
    assert (SNAPSHOT, {"keys", "sources"}, True) in functions


def test_a_store_with_rows_at_010_takes_011(database):
    """A store migrated before 011 gains the setting on the next migrate, with
    its rows kept."""
    with database.admin.begin() as conn:
        conn.execute(text(f"ALTER FUNCTION {SNAPSHOT} RESET plan_cache_mode"))
        # The migration ledger is append-only; only this simulation of an older
        # store goes around that, as the database owner.
        conn.execute(text("SET LOCAL session_replication_role = replica"))
        conn.execute(text("DELETE FROM mdm.migration WHERE name='011_key_list_plans.sql'"))
        conn.execute(text("SET LOCAL session_replication_role = origin"))
        before = {t: conn.scalar(text(f"SELECT count(*) FROM mdm.{t}")) for t in ("policy", "dataset")}
    assert before["policy"] and before["dataset"]
    migrate(database.admin, application_role="clean_application")
    with database.admin.connect() as conn:
        config = conn.scalar(text(f"SELECT proconfig FROM pg_proc WHERE oid = '{SNAPSHOT}'::regprocedure"))
        assert SETTING in config
        assert {t: conn.scalar(text(f"SELECT count(*) FROM mdm.{t}")) for t in before} == before
