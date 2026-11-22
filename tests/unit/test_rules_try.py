"""The try page shows one family's inputs and refuses both save buttons."""
import json

from edgar_warehouse.cli import main
from edgar_warehouse.rules.bench_keep import keep_copy
from edgar_warehouse.rules.bench_store import store_draft
from edgar_warehouse.rules.try_page import (
    FAMILY_DIR,
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


def test_keep_a_copy_and_store_this_draft_refuse_and_write_nothing(tmp_path):
    case = build_case("example", "{}", {"document": "12"}, {"a": 1}, {"a": 1})
    path = tmp_path / "case.json"
    assert keep_copy(case, path) == {"refused": "Keep a copy is not available yet"}
    assert not path.exists()
    assert store_draft(case) == {"refused": "Store this draft is not available yet"}
    assert not path.exists()


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


def test_the_product_family_folder_has_no_family():
    assert families() == []
    assert {path.name for path in FAMILY_DIR.glob("*.py")} == {"__init__.py"}


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


def test_the_save_buttons_on_the_command_refuse(capsys, tmp_path):
    _family(tmp_path)
    path = tmp_path / "saved.json"
    assert main(["rules", "try", "--family", "example", "--families", str(tmp_path),
                 "--button", "Keep a copy", "--path", str(path)]) == 1
    assert json.loads(capsys.readouterr().out) == {"refused": "Keep a copy is not available yet"}
    assert not path.exists()
    assert main(["rules", "try", "--family", "example", "--families", str(tmp_path),
                 "--button", "Store this draft"]) == 1
    assert json.loads(capsys.readouterr().out) == {"refused": "Store this draft is not available yet"}


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
