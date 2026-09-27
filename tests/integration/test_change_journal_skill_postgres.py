"""Skill modes exercise their real interfaces in explicitly isolated stores."""

from __future__ import annotations

import json
from copy import deepcopy

import pytest
from sqlalchemy import text

from edgar_warehouse.bookkeeping.clean.config import Blocked
from edgar_warehouse.change_journal.skill import execute, plan
from edgar_warehouse.infrastructure.sec_client import ConditionalSecResponse
from edgar_warehouse.rules.files import dumps
from tests.integration.test_change_journal_acquisition_postgres import capture_run
from tests.integration.test_configured_bookkeeping_postgres import databases


def test_plan_has_no_live_changes_validate_executes_and_deploy_requires_matching_proof(
    databases, tmp_path, monkeypatch
):
    book, rid, candidate, _, binding, unit = capture_run(
        databases, tmp_path, monkeypatch
    )
    name, rules_ref = binding
    root = tmp_path / "rules-authoring"
    document = book.artifacts.json(rules_ref)["body"]
    path = root / "sources" / name / "source.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(dumps(document))
    with databases.admin.connect() as conn:
        before = conn.scalar(text("SELECT count(*) FROM bookkeeping.pipeline_run"))
    bundle = plan(
        source=name,
        feed="new-feed",
        target="capture",
        inputs=book._run(rid)["submission"]["inputs"],
        rules_root=root,
    )
    with databases.admin.connect() as conn:
        assert (
            conn.scalar(text("SELECT count(*) FROM bookkeeping.pipeline_run")) == before
        )
    for variable, engine in (
        ("BOOKKEEPING_CLEAN_DATABASE_URL", databases.runtime),
        ("RULES_DATABASE_URL", databases.rules.engine),
        ("CHANGE_JOURNAL_DATABASE_URL", databases.ledger.engine),
    ):
        monkeypatch.setenv(variable, engine.url.render_as_string(hide_password=False))
    monkeypatch.setenv(
        "BOOKKEEPING_MANIFEST_ROOT", (tmp_path / "skill-exports").as_uri()
    )
    monkeypatch.delenv("MDM_DATABASE_URL", raising=False)
    calls = []

    def provider(url, identity, *, before_request, **kwargs):
        before_request()
        calls.append(url)
        return ConditionalSecResponse(False, b'{"records":[1]}', None, None)

    monkeypatch.setattr("edgar_warehouse.change_journal.capture._http", provider)
    validated = execute("validate", bundle, source=name, feed="new-feed")
    assert validated["qualified"] is True and validated["verified"] == {"capture": 1}
    assert len(calls) == 1 and len(validated["receipts"]) == 2
    for damaged in (
        None,
        {**validated, "qualified": False},
        {**validated, "feed": "other"},
        {**validated, "plan_hash": "a" * 64},
        {**validated, "verified": {"capture": 0}},
    ):
        with pytest.raises(Blocked):
            execute("deploy", bundle, source=name, feed="new-feed", evidence=damaged)
    deployed = execute(
        "deploy", bundle, source=name, feed="new-feed", evidence=validated
    )
    assert deployed["qualified"] and deployed["run_id"] == validated["run_id"]
    assert (
        len(calls) == 1
    )  # verified completed units are rechecked, never fetched again
    with pytest.raises(Blocked):
        execute("validate", bundle, source=name, feed="other")
    monkeypatch.setenv(
        "BOOKKEEPING_CLEAN_DATABASE_URL",
        "postgresql://runtime@production.invalid/bookkeeping_clean",
    )
    with pytest.raises(Blocked):
        execute("validate", bundle, source=name, feed="new-feed")
