"""Real PG16: a master's detail rows (ticket 120; operator, 2026-10-20: "Detail rows set
in config (Recommended)", "One set, joined by FIGI (Recommended)", "End it, keep
history (Recommended)").

Two sources' records of one master each carry rows of one list, keyed: the master
holds one row per key, from the first source in the kind's order, naming every
source that gave the key; `mdm.detail_version` keeps every row, and a row no source
carries any more is ended, its history kept. A master whose records carry no rows
has no `details` at all. The masters are Securities: a Company is kept in
mdm.company's columns, so its contracts state no detail lists. Invented values only.
"""

from __future__ import annotations

from sqlalchemy import text

from tests.integration import test_clean_mdm_postgres as core
from tests.integration.test_clean_identifier_binding import load, matching_policy


def securities(database):
    return {k: v for k, v in core.documents(database, "entity").items() if v["kind"] == "security"}


def record(key, source_code="fixture.primary", revision=1, details=None, name=None):
    return core.source(key=key, source_code=source_code, revision=revision, kind="security",
                       fields={"name": name or f"Security {key}"}, identifiers={"cik": "0000320193"}, details=details)


def row(key, place, ticker):
    return {"key": key, "exchange": place, "ticker": ticker}


def versions(database):
    with database.application.connect() as conn:
        return [dict(r._mapping) for r in conn.execute(text(
            "SELECT detail, key, from_generation, to_generation, body FROM mdm.detail_version "
            "ORDER BY key, from_generation"))]


def test_one_row_per_key_from_the_first_source_with_every_source_named(database):
    policy = matching_policy(database, kind="security")
    load(database, policy, "b1",
         record("a", details={"listings": [row("F1", "US", "AAA"), row("F2", "LN", "AAB")]}),
         record("b", "fixture.secondary", details={"listings": [row("F2", "LN", "XXX"), row("F3", "GR", "AAC")]}))
    (security,) = securities(database).values()

    assert security["details"] == {"listings": [
        {"key": "F1", "exchange": "US", "ticker": "AAA", "sources": ["fixture.primary"]},
        # Both give F2: the first source in the kind's order gives the row.
        {"key": "F2", "exchange": "LN", "ticker": "AAB", "sources": ["fixture.primary", "fixture.secondary"]},
        {"key": "F3", "exchange": "GR", "ticker": "AAC", "sources": ["fixture.secondary"]}]}
    found = versions(database)
    assert [(v["detail"], v["key"], v["to_generation"]) for v in found] == [
        ("listings", "F1", None), ("listings", "F2", None), ("listings", "F3", None)]
    assert found[1]["body"] == security["details"]["listings"][1]


def test_a_row_no_source_gives_any_more_is_ended_and_kept(database):
    policy = matching_policy(database, kind="security")
    load(database, policy, "b1", record("a", details={"listings": [row("F1", "US", "AAA"), row("F2", "LN", "AAB")]}))
    (before,) = versions(database)[:1]
    load(database, policy, "b2", record("a", revision=2, details={"listings": [row("F1", "US", "AAZ")]}), checkpoint=2)
    (security,) = securities(database).values()

    assert [r["key"] for r in security["details"]["listings"]] == ["F1"]
    found = versions(database)
    f1 = [v for v in found if v["key"] == "F1"]
    f2 = [v for v in found if v["key"] == "F2"]
    # F1 changed: its first state closed, the new one open.
    assert [v["to_generation"] is None for v in f1] == [False, True] and f1[0]["body"] == before["body"]
    assert f1[1]["body"]["ticker"] == "AAZ"
    # F2 is gone from the source: ended, its one state kept.
    assert len(f2) == 1 and f2[0]["to_generation"] == f1[0]["to_generation"]


def test_a_master_whose_records_carry_no_rows_has_no_details(database):
    policy = matching_policy(database, kind="security")
    load(database, policy, "b1", record("a"))
    (security,) = securities(database).values()

    assert "details" not in security and versions(database) == []


def test_a_field_change_leaves_the_detail_rows_alone(database):
    """Standards review: the trigger fires only when the details change."""
    policy = matching_policy(database, kind="security")
    listings = {"listings": [row("F1", "US", "AAA")]}
    load(database, policy, "b1", record("a", details=listings))
    before = versions(database)
    load(database, policy, "b2", record("a", revision=2, details=listings, name="Renamed"), checkpoint=2)
    (security,) = securities(database).values()

    assert security["fields"]["name"]["value"] == "Renamed"
    assert versions(database) == before

