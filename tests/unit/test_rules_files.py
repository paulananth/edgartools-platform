"""Rules files hold JSON values exactly: what a reader sees is what a digest covers."""

from __future__ import annotations

import pytest

from edgar_warehouse.mdm.store import canonical
from edgar_warehouse.rules.files import RulesFileError, dumps, loads

# Strings that plain YAML would read as something else, or that need quoting.
TRICKY_TEXT = [
    "1", "8", "10", "010", "6189", "1e5", "1.0", "-3", "0x1F", "1_000", "12:30",
    "2026-09-25", "2026-09-25T17:09:33Z", "2026-09-25.13",
    "yes", "no", "on", "off", "y", "n", "Yes", "TRUE", "True", "Null", "null",
    "true", "false", "~", "", " ", ".inf", ".nan",
    "a: b", "#x", "- x", "'q'", '"dq"', "  lead", "trail ", "multi\nline", "é",
    "sec.company.v1", "Entity.LegalName.$",
]
VALUES = [0, 1, -3, 600, 1.5, 0.995511, 0.9910621278248719, 1e-05, 1e16, None,
          True, False, [], {}, {"8": {"n": 300}}, [{"a": [1, "1", None]}]]


@pytest.mark.parametrize("value", TRICKY_TEXT + VALUES)
def test_a_value_reads_back_exactly(value):
    back = loads(dumps({"k": value}))["k"]
    assert type(back) is type(value)
    assert canonical(back) == canonical(value)


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("k: yes", "'yes' is ambiguous"),
        ("k: 010", "'010' is ambiguous"),
        ("k: 2026-09-25", "'2026-09-25' is ambiguous"),
        ("k:", "an empty value is ambiguous"),
        ("k: ~", "'~' is ambiguous"),
        ("k: .inf", "'.inf' is ambiguous"),
        ("a: &x 1\nb: *x", "anchors and aliases"),
        ("k: !!str 1", "tags are not allowed"),
        ("k: !!map {b: 1}", "tags are not allowed"),
        ("k: !!seq [1]", "tags are not allowed"),
        ("--- !!map\nk: 1", "tags are not allowed"),
        ("k: ! yes", "tags are not allowed"),
        ("a: 1\na: 2", "duplicate key 'a'"),
        ("? [1]\n: 2", "a key must be text"),
    ],
)
def test_an_ambiguous_file_is_refused_with_its_line(text, reason):
    with pytest.raises(RulesFileError, match=reason) as error:
        loads(text, "f.yaml")
    assert str(error.value).startswith("f.yaml:")


def test_a_second_document_is_refused():
    with pytest.raises(RulesFileError, match="single document"):
        loads("a: 1\n---\nb: 2\n")


def test_a_key_is_always_text():
    assert loads("8: a\ntrue: b\nnull: c") == {"8": "a", "true": "b", "null": "c"}


def test_plain_json_literals_are_typed():
    assert loads("a: null\nb: true\nc: 600\nd: 0.95\ne: 1e-5") == {
        "a": None, "b": True, "c": 600, "d": 0.95, "e": 1e-05,
    }


def test_python_backend_fallback_preserves_rules_round_trips(monkeypatch):
    import yaml
    from edgar_warehouse.rules import files
    monkeypatch.setattr(files, "_RULES_LOADER", yaml.SafeLoader)
    for value in TRICKY_TEXT + VALUES:
        back = files.loads(files.dumps({"k": value}))["k"]
        assert type(back) is type(value)
        assert canonical(back) == canonical(value)
    for text in ("a: &x 1\nb: *x", "k: !!str 1", "a: 1\na: 2", "k: yes", "a: 1\n---\nb: 2"):
        with pytest.raises(RulesFileError):
            files.loads(text)


@pytest.mark.parametrize("escaped,expected", [("\\ud800", "\ud800"), ("\\ud83d\\ude00", "\ud83d\ude00")])
def test_compiled_parser_refusal_preserves_existing_surrogate_reader_values(escaped, expected):
    assert loads(f'k: "{escaped}"') == {"k": expected}


@pytest.mark.parametrize("text", ["k: a\tb", "k\t: v", "k: a\t\nz: b"])
def test_unquoted_tabs_keep_existing_scanner_refusals(text):
    with pytest.raises(RulesFileError):
        loads(text)


@pytest.mark.parametrize("text", ['k: "a\tb"', "k: 'a\tb'", "k: |\n  a\tb\n"])
def test_quoted_and_block_tabs_keep_existing_values(text):
    import yaml
    from edgar_warehouse.rules import files
    expected = files._value(files._rules_node(text, "<rules>", yaml.SafeLoader), "<rules>")
    assert loads(text) == expected


def _policy_folder(root, kinds: dict, shared: dict) -> None:
    (root / "merge" / "kinds").mkdir(parents=True)
    (root / "merge" / "policy.yaml").write_text(dumps({"version": "invented"}))
    (root / "merge" / "lists.yaml").write_text(dumps(shared))
    for name, kind in kinds.items():
        (root / "merge" / "kinds" / f"{name}.yaml").write_text(dumps(kind))


def test_a_kind_takes_each_shared_list_its_rules_name_and_an_export_keeps_it_shared(tmp_path):
    from edgar_warehouse.rules import files

    naming = {"rules": [{"steps": [{"when": [{"args": {"token_list": "legal_form"}}]}]}], "lists": {"own": ["X"]}}
    _policy_folder(tmp_path / "in", {"naming": naming, "silent": {"rules": []}}, {"legal_form": ["INC", "LLC"]})
    body = files.policy(tmp_path / "in")
    assert body["kinds"]["naming"]["lists"] == {"own": ["X"], "legal_form": ["INC", "LLC"]}
    assert "lists" not in body["kinds"]["silent"]
    files.write_policy(body, tmp_path / "out")
    assert files.load(tmp_path / "out" / "merge" / "kinds" / "naming.yaml")["lists"] == {"own": ["X"]}
    assert canonical(files.policy(tmp_path / "out")) == canonical(body)


def test_a_kind_declaring_a_list_of_a_shared_name_is_refused(tmp_path):
    from edgar_warehouse.rules import files

    _policy_folder(tmp_path, {"copying": {"rules": [], "lists": {"legal_form": ["INC"]}}}, {"legal_form": ["INC", "LLC"]})
    with pytest.raises(RulesFileError, match="copying declares the shared lists"):
        files.policy(tmp_path)
