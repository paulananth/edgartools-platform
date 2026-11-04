"""The `context` command without a database (profiling ticket 05): definitions
cover every kind and relationship type, answers stay within 8 KB in bytes, and
no output holds a database address or password."""

from __future__ import annotations

import json

import pytest

from edgar_warehouse import context
from edgar_warehouse.cli import build_parser, main
from edgar_warehouse.mdm.evidence import KINDS
from edgar_warehouse.rules import files

def test_every_kind_and_relationship_type_has_a_definition():
    defined = context.definitions()
    from edgar_warehouse.mdm.catalog import CATALOG
    assert set(CATALOG["kinds"]) == KINDS
    assert {k for k, v in defined["kinds"].items() if v.strip()} == KINDS
    from edgar_warehouse.mdm.relationships import types_of

    types = types_of(files.policy())
    assert {t for t, v in context.relationship_definitions().items() if v.strip()} == set(types)
    assert "relationships" not in defined  # the code set holds their words (ticket 132)


def test_definitions_are_not_part_of_the_mastering_policy():
    body = files.policy()
    assert "context" not in body and "definitions" not in json.dumps(sorted(body))


def answer_with(items):
    return {"name": "x", "items": items, "truncated": False, "next_page": None, "next_step": "done"}


def test_the_limit_is_counted_in_bytes_and_cut_at_a_whole_item():
    items = [{"n": i, "text": "é" * 300} for i in range(40)]  # 2 bytes a character
    first = context.fit(answer_with(items), "items", 0, "cmd")
    assert len(json.dumps(first, ensure_ascii=False).encode()) <= context.LIMIT_BYTES
    assert first["truncated"] and first["next_page"] == f"p{len(first['items'])}"
    assert first["next_step"] == f"cmd --page {first['next_page']}"
    assert first["items"] == items[: len(first["items"])]
    rest = context.fit(answer_with(items), "items", context.page_offset(first["next_page"]), "cmd")
    assert rest["items"][0] == items[len(first["items"])]
    with pytest.raises(context.ContextError):
        context.fit(answer_with(items), "items", 41, "cmd")


def test_a_long_value_is_clipped_and_says_so():
    shown = context.fit(answer_with([{"text": "y" * 5000}]), "items", 0, "cmd")
    assert shown["clipped"] and len(shown["items"][0]["text"]) == context.CLIP + 1


@pytest.mark.parametrize("page", ["2", "page2", "p-1", "p1234567"])
def test_a_bad_page_token_says_what_to_pass(page):
    with pytest.raises(context.ContextError) as error:
        context.page_offset(page)
    assert "next_page" in error.value.command


def test_a_time_needs_a_zone():
    with pytest.raises(context.ContextError) as error:
        context.parse_time("2026-01-31", "--as-of", "edgar-warehouse context company x")
    assert error.value.command == "edgar-warehouse context company x --as-of 2026-01-31T00:00:00+00:00"


def test_the_command_is_registered():
    args = build_parser().parse_args(["context", "company", "--search", "acme", "--limit", "3"])
    assert args.subject == "company" and args.search == "acme" and args.limit == 3


def test_no_output_holds_the_database_address(monkeypatch, capsys):
    monkeypatch.setenv("MDM_DATABASE_URL", "postgresql+psycopg2://agentlogin:s3cretpw@127.0.0.1:1/mdmstore")
    code = main(["context", "company", "--search", "acme"])
    out, err = capsys.readouterr()
    assert code == 1 and json.loads(out)["try"]
    for secret in ("agentlogin", "s3cretpw", "127.0.0.1", "mdmstore"):
        assert secret not in out and secret not in err


def test_a_missing_login_says_what_to_set(monkeypatch, capsys):
    monkeypatch.delenv("MDM_DATABASE_URL", raising=False)
    assert main(["context", "company", "x"]) == 2
    assert "MDM_DATABASE_URL" in json.loads(capsys.readouterr().out)["error"]


def test_an_item_too_big_for_a_page_is_an_error_not_a_loop():
    big = answer_with([{"text": "z" * 900} for _ in range(3)])
    big.update({f"note_{i}": "n" * 999 for i in range(7)})  # under the clip, together near 7 KB
    big["items"] = [{"text": "z" * 1000} for _ in range(3)]  # each item alone overflows what is left
    with pytest.raises(context.ContextError):
        context.fit(big, "items", 0, "cmd")


def test_relationship_definitions_come_from_the_code_set_the_given_policy_pins(monkeypatch):
    """Ticket 140: the answer's words are those of the policy its generation ran under, not the repo's pin."""
    asked = []

    def published(pin, root=None):
        asked.append(pin)
        return [{"code": "OWNS", "parent_code": None, "definition": "The pinned words."},
                {"code": "OWNS:director", "parent_code": "OWNS", "definition": "A capacity, not a type."}]

    monkeypatch.setattr(files, "published_reference", published)
    pin = {"code_set": "mdm-relationship-types", "version": 7, "sha256": "f" * 64}
    policy = {"relationships": {"pin": "relationships"}, "reference_pins": {"relationships": pin}}
    assert context.relationship_definitions(policy) == {"OWNS": "The pinned words."}
    assert asked == [pin]
    assert context.relationship_definitions({"kinds": {}}) == {}  # a policy pinning none has no types


def test_the_policy_of_a_generation_is_found_by_its_digest():
    from edgar_warehouse.mdm.store import digest

    class Adapter:
        def registered_policies(self, conn):
            return [{"kinds": {"a": 1}}, {"kinds": {"b": 2}}]

    wanted = {"kinds": {"b": 2}}
    assert context.policy_of(Adapter(), None, digest(wanted)) == wanted
    assert context.policy_of(Adapter(), None, "0" * 64) is None
    assert context.policy_of(Adapter(), None, None) is None
