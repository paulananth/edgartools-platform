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
    # The engine's refusal keeps its own words; the loader's names only its kind.
    assert results["source:example.bad-target"].startswith("refused (Blocked): A target requires steps")
    assert results["source:example.guessed"].startswith("refused (RulesFileError)")
    assert results["merge:platform"] == "ok"


def test_a_refusal_never_quotes_the_file(root):
    write(root, "example.guessed", "source: example.guessed\nprivate_note: 2026-10-18\n")

    assert "2026-10-18" not in files.check(["example.guessed"], root)["source:example.guessed"]


def test_named_sources_only_and_a_missing_one_is_refused(root):
    write(root, "example.good", files.dumps({"source": "example.good"}))

    assert files.check(["example.good", "example.absent"], root) == {
        "source:example.good": "ok",
        "source:example.absent": f"refused (missing): no {root}/sources/example.absent/source.yaml"}


def test_a_body_that_is_not_json_is_refused():
    with pytest.raises(files.RulesFileError, match="not JSON"):
        files.check_document("source", {"source": "example", "when": ("a", "b")})


def test_save_refuses_what_check_refuses_before_writing():
    from edgar_warehouse.control_contract import Blocked
    from edgar_warehouse.mdm.clean.store import Conflict
    from edgar_warehouse.rules.db import Rules

    rules = Rules(engine=None)  # a refusal comes before any database work
    with pytest.raises(Blocked, match="A target requires steps"):
        rules.save("source", "example", "1", {"source": "example",
                                               "bookkeeping": {"version": 1, "targets": {"mastering": {"steps": []}}}})
    policy = files.policy()
    policy["kinds"]["company"]["rules"] = policy["kinds"]["company"]["rules"] * 2
    with pytest.raises(Conflict, match="Rule .* version .*"):
        rules.save("merge", "platform", "1", policy)
