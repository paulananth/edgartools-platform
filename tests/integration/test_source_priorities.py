"""Real PG16: a file with a source its kind's fill rule leaves out is refused, and nothing is stored."""

import copy

import pytest
from sqlalchemy import text

from tests.integration import test_mdm_postgres as core
from tests.support import masters

CODE = "invented.listed.v1"
OTHER = "invented.unlisted.v1"
POLICY = {"version": 1, "required_consumers": ["export"], "automatic_rules": [],
          "kinds": {"company": {"version": "1", "defaults": {"sources": [CODE]},
                                "fields": {"name": {"sources": [CODE]}}}}}


def record(code: str, key: str) -> dict:
    return core.source(key=key, source_code=code, kind="company", fields={"name": key}, identifiers={"cik": key})


def held(database) -> int:
    with database.application.connect() as conn:
        return conn.execute(text("SELECT count(*) FROM mastering_record")).scalar()


def test_a_source_the_kinds_fill_rule_leaves_out_is_refused_and_nothing_is_stored(database):
    with pytest.raises(ValueError, match=f"company policy has no source priority for: {OTHER}"):
        masters.seed(database.application, [record(CODE, "0000000001"), record(OTHER, "0000000002")], copy.deepcopy(POLICY))
    assert held(database) == 0


def test_a_file_of_listed_sources_is_merged(database):
    masters.seed(database.application, [record(CODE, "0000000001")], copy.deepcopy(POLICY))
    assert held(database) == 1
