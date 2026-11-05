"""The operator's approvals kept in git (ticket 193): read, written for every rules document at its digest, and a
rules change that has no line yet. Every name here is invented or a committed rules folder copied to a temp folder."""
import shutil

import pytest
import yaml

from edgar_warehouse.rules import approvals, files


@pytest.fixture
def root(tmp_path):
    shutil.copytree(files.ROOT / "sources/sec.thirteenf.filings", tmp_path / "sources/sec.thirteenf.filings")
    return tmp_path


WORDS = dict(by="Operator", words="approved all rules", finalized="PR 1", at="2026-11-04")


def test_a_folder_with_no_approvals_file_lists_none_and_every_document_is_missing(root):
    assert approvals.read(root) == []
    assert [(k, n) for k, n, _ in approvals.missing(root)] == [("source", "sec.thirteenf.filings")]


def test_write_lists_each_document_at_its_digest_in_the_operators_words_and_check_then_passes(root):
    (entry,) = approvals.write(root, **WORDS)
    assert entry == {"kind": "source", "name": "sec.thirteenf.filings", "digest": approvals.current(root)[0][2], **WORDS}
    assert approvals.missing(root) == []
    assert yaml.safe_load((root / approvals.FILE).read_text())["approvals"] == [entry]


def test_a_rules_change_is_a_new_digest_with_no_approval_until_it_is_written(root):
    approvals.write(root, **WORDS)
    path = root / "sources/sec.thirteenf.filings/source.yaml"
    path.write_text(path.read_text() + "\n# a comment changes nothing\n")
    assert approvals.missing(root) == []  # comments are authoring metadata: the digest is of the canonical rules
    body = yaml.safe_load(path.read_text())
    body["note"] = "a changed rule"
    path.write_text(yaml.dump(body))
    assert [n for _, n, _ in approvals.missing(root)] == ["sec.thirteenf.filings"]
    kept = approvals.write(root, **{**WORDS, "words": "approved the change", "finalized": "PR 2"})
    assert [e["words"] for e in kept] == ["approved the change"]  # the old digest's line is dropped with its document


@pytest.mark.parametrize("entry", [{"kind": "source"}, {"kind": "nope", "name": "x", "digest": "0" * 64, **WORDS},
                                   {"kind": "source", "name": "x", "digest": "short", **WORDS},
                                   {"kind": "source", "name": "x", "digest": "0" * 64, **{**WORDS, "words": " "}}])
def test_a_malformed_line_refuses_the_file(root, entry):
    (root / approvals.FILE).write_text(yaml.dump({"version": 1, "approvals": [entry]}))
    with pytest.raises(ValueError):
        approvals.read(root)
