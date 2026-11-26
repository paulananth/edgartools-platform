"""The try page shows one family's inputs. Keep a copy writes a confirmed path.
Store this draft keeps a versioned draft."""
import json
from pathlib import Path

from edgar_warehouse.cli import main
from edgar_warehouse.rules.bench_keep import keep_copy
from edgar_warehouse.rules.bench_store import store_draft
from edgar_warehouse.rules.try_page import (
    attempt,
    build_case,
    families,
    load_full,
    matches,
    present,
    press,
    show_full,
)


def _family(folder, *, title="Example family", label="Document you paste", extra=""):
    (folder / "example.py").write_text(
        f"title = {title!r}\n"
        f"inputs = [{{'name': 'document', 'label': {label!r}}}]\n"
        f"{extra}"
    )


def test_a_family_appears_only_because_its_file_exists(tmp_path):
    assert families(tmp_path) == []
    bomb = tmp_path / "example_full.py"
    bomb.write_text("raise RuntimeError('do not load the short words alone')\n")
    assert families(tmp_path) == []
    assert load_full("example", tmp_path) is None
    bomb.unlink()
    _family(tmp_path)
    assert families(tmp_path) == ["example"]
    assert load_full("example", tmp_path) is None


def test_short_words_are_used_only_when_the_family_file_exists(tmp_path):
    (tmp_path / "example_full.py").write_text(
        "words = [{'word': 'exact decimal', 'stored': 'value'}]\n"
    )
    assert load_full("example", tmp_path) is None
    _family(tmp_path)
    page = present("example", tmp_path)
    assert "exact decimal" in page
    assert "value" in page
    assert show_full("example", "", tmp_path) == {
        "lines": [{"word": "exact decimal", "stored": "value"}],
    }


def test_fake_family_shows_its_title_inputs_rule_and_expected_output(tmp_path):
    _family(tmp_path, title="<Example & family>", label="<Document you paste>")
    page = present("example", tmp_path)
    assert "&lt;Example &amp; family&gt;" in page
    assert "&lt;Document you paste&gt;" in page
    assert "<Example" not in page
    assert ">Rule<" in page
    assert "Expected output" in page
    for button in ("Try", "Show the full rule", "Keep a copy", "Store this draft"):
        assert f">{button}<" in page


def test_compare_ignores_key_order_and_keeps_list_order():
    assert matches({"b": 1, "a": 2}, {"a": 2, "b": 1})
    assert not matches({"a": 1}, {"a": 2})
    assert not matches([1, 2], [2, 1])
    assert matches({"a": None}, {"a": None})
    assert not matches({"a": None}, {"a": ""})
    assert not matches({"a": 0}, {"a": False})


def test_a_confirmed_path_reloads_as_the_same_json(tmp_path):
    case = {"b": 1, "a": {"name": "Example Works", "quantity": 12}}
    path = tmp_path / "case.json"
    assert keep_copy(case, path) == {"kept": str(path)}
    assert json.loads(path.read_text()) == case


def test_an_unconfirmed_path_is_not_written(tmp_path):
    case = {"family": "example", "rule": "{}"}
    path = tmp_path / "case.json"
    assert keep_copy(case, None) == {"refused": "The path is not confirmed."}
    assert not path.exists()


def test_keep_a_copy_without_a_path_does_not_write(capsys, tmp_path):
    _family(tmp_path)
    assert main(["rules", "try", "--family", "example", "--families", str(tmp_path),
                 "--button", "Keep a copy"]) == 1
    assert json.loads(capsys.readouterr().out) == {"refused": "The path is not confirmed."}
    assert list(tmp_path.glob("*.json")) == []


def test_a_copy_is_not_written_under_rules():
    from edgar_warehouse.rules.files import ROOT

    target = Path(ROOT) / "not-a-kept-copy.json"
    case = {"family": "example", "rule": "{}"}
    try:
        assert keep_copy(case, target) == {"refused": "A copy is not written under rules/."}
        assert not target.exists()
    finally:
        if target.exists():
            target.unlink()


def test_a_differently_cased_rules_folder_is_not_written():
    import os
    from edgar_warehouse.rules.files import ROOT

    root = Path(ROOT)
    alias = root.with_name(root.name.swapcase())
    if not (alias.exists() and os.path.samefile(alias, root)):
        return
    target = alias / "not-a-kept-copy.json"
    try:
        assert keep_copy({"family": "example"}, target) == {"refused": "A copy is not written under rules/."}
        assert not target.exists()
    finally:
        if target.exists():
            target.unlink()


def test_a_missing_folder_is_not_written(tmp_path):
    target = tmp_path / "missing" / "case.json"
    assert keep_copy({"family": "example"}, target) == {"refused": "The folder is not there."}
    assert not target.exists()


def test_a_folder_path_is_not_written(tmp_path):
    folder = tmp_path / "case"
    folder.mkdir()
    assert keep_copy({"family": "example"}, folder) == {"refused": "The path is a folder."}
    assert not any(folder.iterdir())


def _rules_engine(tmp_path, monkeypatch):
    from sqlalchemy import create_engine

    from edgar_warehouse.rules.db import migrate

    engine = create_engine(f"sqlite:///{tmp_path / 'rules.db'}")
    migrate(engine)
    monkeypatch.setattr("edgar_warehouse.rules.db.get_engine", lambda url=None: engine)
    return engine


def test_a_rule_with_no_version_is_not_stored(monkeypatch):
    def opened(url=None):
        raise AssertionError("database opened")

    monkeypatch.setattr("edgar_warehouse.rules.db.get_engine", opened)
    for rule in ("", "{}", '{"trim": "quantity"}', "not json", '{"version": ""}',
                 '{"version": "   "}', '{"version": 1}', "[]"):
        assert store_draft(build_case("example", rule, {}, None, None)) == {
            "refused": "The version label is not there."
        }
    assert store_draft(build_case("example", json.dumps({"version": "v" * 129}), {}, None, None)) == {
        "refused": "The version label is too long."
    }
    assert store_draft({"rule": '{"version": "draft-1"}'}) == {"refused": "The draft is not stored."}


def test_a_draft_is_stored_under_the_typed_version_and_the_case_stays_beside_it(tmp_path, monkeypatch):
    engine = _rules_engine(tmp_path, monkeypatch)
    rule = '{"trim": "quantity", "version": "draft-1"}'
    case = build_case("example", rule, {"document": "12"}, {"a": 1}, {"a": 1})
    stored = store_draft(case)
    assert stored == {
        "digest": "d7097b4a191ff17f3098239ce47cc828375d3dc088e6b3ad1ee6178019a6e9fb",
        "status": "draft",
        "stored": "draft-1",
    }
    from edgar_warehouse.rules.db import Rules

    found = Rules(engine).draft("try", "example", "draft-1")
    assert found["status"] == "draft"
    assert found["body"] == {"trim": "quantity", "version": "draft-1"}
    assert found["case"] == case
    again = build_case("example", rule, {"document": "99"}, {"a": 1}, {"a": 1})
    assert store_draft(again) == stored
    assert Rules(engine).draft("try", "example", "draft-1")["case"] == case
    other = build_case("example", '{"trim": "other", "version": "draft-1"}', {}, None, None)
    assert store_draft(other) == {"refused": "This version is already stored."}
    assert Rules(engine).draft("try", "example", "draft-1")["body"] == {
        "trim": "quantity", "version": "draft-1"}


def test_try_refuses_until_the_family_can_run_and_returns_one_object(tmp_path):
    _family(tmp_path)
    assert attempt("example", "", {}, tmp_path) == {"refused": "This family cannot be tried yet."}
    _family(tmp_path, extra=(
        "def run(inputs, rule):\n"
        "    return {'b': 1, 'a': inputs['document']}\n"
    ))
    assert attempt("example", "", {"document": "12"}, tmp_path) == {"b": 1, "a": "12"}
    tried = press("Try", "example", inputs={"document": "12"}, expected={"a": "12", "b": 1},
                  directory=tmp_path)
    assert tried["passed"] is True
    assert tried["actual"] == {"b": 1, "a": "12"}
    _family(tmp_path, extra="def run(inputs, rule):\n    return [1]\n")
    assert attempt("example", "", {}, tmp_path) == {"refused": "The result is not one JSON object."}


def test_every_product_family_declares_a_page():
    for name in families():
        assert present(name)


def test_rules_try_names_the_family_and_does_not_open_a_database(capsys, monkeypatch):
    def opened(*_args, **_kwargs):
        raise AssertionError("database opened")

    monkeypatch.setattr("edgar_warehouse.database_connections.connect", opened)
    monkeypatch.setattr("edgar_warehouse.rules.files.load", opened)
    assert main(["rules", "try"]) == 1
    assert json.loads(capsys.readouterr().out) == {"refused": "Name the family to try."}


def test_rules_try_shows_the_page_for_a_family_in_a_temp_folder(capsys, tmp_path, monkeypatch):
    def opened(*_args, **_kwargs):
        raise AssertionError("rules read")

    monkeypatch.setattr("edgar_warehouse.rules.files.load", opened)
    _family(tmp_path)
    assert main(["rules", "try", "--family", "example", "--families", str(tmp_path)]) == 0
    page = capsys.readouterr().out
    assert "Example family" in page
    assert "Document you paste" in page
    assert "Expected output" in page


def test_a_missing_family_is_refused(capsys, tmp_path):
    assert main(["rules", "try", "--family", "missing", "--families", str(tmp_path)]) == 1
    assert json.loads(capsys.readouterr().out) == {"refused": "No family named missing."}


def test_keep_a_copy_on_the_command_reloads_as_the_same_json(capsys, tmp_path):
    _family(tmp_path)
    path = tmp_path / "saved.json"
    assert main(["rules", "try", "--family", "example", "--families", str(tmp_path),
                 "--button", "Keep a copy", "--path", str(path)]) == 0
    assert json.loads(capsys.readouterr().out) == {"kept": str(path)}
    assert json.loads(path.read_text()) == {
        "actual": None,
        "expected": None,
        "family": "example",
        "inputs": {},
        "passed": True,
        "rule": "",
    }


def test_store_this_draft_on_the_command_refuses_without_a_version(capsys, tmp_path, monkeypatch):
    def opened(url=None):
        raise AssertionError("database opened")

    monkeypatch.setattr("edgar_warehouse.rules.db.get_engine", opened)
    _family(tmp_path)
    assert main(["rules", "try", "--family", "example", "--families", str(tmp_path),
                 "--button", "Store this draft"]) == 1
    assert json.loads(capsys.readouterr().out) == {"refused": "The version label is not there."}


def test_store_this_draft_on_the_command_stores_the_typed_version(capsys, tmp_path, monkeypatch):
    _family(tmp_path)
    engine = _rules_engine(tmp_path, monkeypatch)
    rule = '{"version": "draft-1"}'
    assert main(["rules", "try", "--family", "example", "--families", str(tmp_path),
                 "--button", "Store this draft", "--rule", rule]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["stored"] == "draft-1"
    assert result["status"] == "draft"
    from edgar_warehouse.rules.db import Rules

    found = Rules(engine).draft("try", "example", "draft-1")
    assert found["body"] == {"version": "draft-1"}
    assert found["status"] == "draft"
    assert found["case"]["rule"] == rule
    assert found["case"]["family"] == "example"
    assert found["case"]["passed"] is True
    assert result["digest"] == found["digest"]


def test_show_the_full_rule_refuses_when_the_family_has_no_short_words(tmp_path):
    _family(tmp_path)
    assert show_full("example", "", tmp_path) == {"refused": "This family has no short words yet."}


def test_show_the_full_rule_calls_explain_when_the_short_word_file_defines_it(tmp_path):
    _family(tmp_path)
    (tmp_path / "example_full.py").write_text(
        "def explain(rule):\n"
        "    return {'lines': [{'word': 'exact decimal', 'stored': 'value'}], 'rule': rule}\n"
    )
    assert show_full("example", "exact decimal", tmp_path) == {
        "lines": [{"word": "exact decimal", "stored": "value"}],
        "rule": "exact decimal",
    }
