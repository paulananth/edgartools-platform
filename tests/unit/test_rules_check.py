"""`rules check`: every rules file checked as `rules save` would, offline (ticket 16, item 6)."""
import shutil

import pytest

from edgar_warehouse.rules import files

# A target that holds: the one a repository source declares.
TARGET = files.source("sec.submissions.person")["bookkeeping"]


@pytest.fixture
def root(tmp_path):
    shutil.copytree(files.ROOT / "merge", tmp_path / "merge")
    shutil.copytree(files.ROOT / "identifiers", tmp_path / "identifiers")
    return tmp_path


def write(root, name, text):
    (root / "sources" / name).mkdir(parents=True)
    (root / "sources" / name / "source.yaml").write_text(text)


def test_the_repository_rules_all_hold():
    results = files.check()

    assert results and set(results.values()) == {"ok"}
    assert "merge:platform" in results


def test_each_refusal_is_named_and_the_rest_still_checked(root):
    write(root, "example.good", files.dumps({"source": "example.good", "bookkeeping": TARGET}))
    write(root, "example.bad-target", files.dumps({"source": "example.bad-target",
                                                   "bookkeeping": {"version": 1, "targets": {"mastering": {"steps": []}}}}))
    write(root, "example.guessed", "source: example.guessed\nenabled: yes\n")

    results = files.check(root=root)

    assert results["source:example.good"] == "ok"
    assert results["source:example.bad-target"].startswith("refused (Blocked)")
    assert results["source:example.guessed"].startswith("refused (RulesFileError)")
    assert results["merge:platform"] == "ok"


def test_a_refusal_never_quotes_the_file(root):
    write(root, "example.guessed", "source: example.guessed\nprivate_note: 2026-10-18\n")

    assert "2026-10-18" not in files.check(["example.guessed"], root)["source:example.guessed"]


def test_named_sources_only_and_a_missing_one_is_refused(root):
    write(root, "example.good", files.dumps({"source": "example.good"}))

    assert files.check(["example.good", "example.absent"], root) == {
        "source:example.good": "ok",
        "source:example.absent": "refused (missing): no rules/sources/<name>/source.yaml"}


def test_save_refuses_what_check_refuses():
    with pytest.raises(files.RulesFileError, match="read back"):
        files.check_document("source", {"source": "example", "when": ("a", "b")})
