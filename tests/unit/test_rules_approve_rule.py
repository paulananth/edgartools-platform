"""One merge rule is switched on by the operator's words, on its proof, and the
policy keeps its comments (rules skill ticket 14)."""
from __future__ import annotations

import shutil

import pytest

from edgar_warehouse.mdm.clean.activation import activated, check_policy
from edgar_warehouse.mdm.clean.store import Conflict
from edgar_warehouse.rules import files
from edgar_warehouse.rules.cli import register

RULE = "sec-gleif-name-jurisdiction"
AT = "2026-09-29T23:30:00Z"


@pytest.fixture
def root(tmp_path):
    shutil.copytree(files.ROOT, tmp_path / "rules")
    return tmp_path / "rules"


def test_a_rule_is_switched_on_with_its_proof_and_the_operator_words(root):
    before = (root / "merge" / "policy.yaml").read_text()
    entry = files.approve_rule(RULE, by="Operator", words="Yes, switch the name-and-state rule on", at=AT, root=root)
    after = (root / "merge" / "policy.yaml").read_text()
    assert after.startswith(before.rstrip("\n"))  # comments kept, nothing rewritten
    assert f"# {RULE}: switched on by Operator, {AT}" in after
    body = files.policy(root)
    check_policy(body)
    assert body["automatic_rules"][-1] == entry
    assert entry["proof"] == {**files.pending_proofs(root)[RULE], "approved_by": "Operator", "approved_at": AT,
                              "approved_words": "Yes, switch the name-and-state rule on"}
    rule = next(r for r in body["kinds"]["company"]["rules"] if r["rule_id"] == RULE)
    assert activated(body, "company", rule, "bind")
    with pytest.raises(files.RulesFileError, match="already switched on"):
        files.approve_rule(RULE, by="Operator", words="again", at=AT, root=root)


def test_no_rule_is_switched_on_without_evidence_or_words(root):
    unchanged = (root / "merge" / "policy.yaml").read_text()
    with pytest.raises(files.RulesFileError, match="No test evidence"):
        files.approve_rule("company-cik", by="Operator", words="yes", at=AT, root=root)
    with pytest.raises(files.RulesFileError, match="exact words"):
        files.approve_rule(RULE, by="Operator", words=" ", at=AT, root=root)
    assert (root / "merge" / "pending-proofs.yaml").exists()
    assert (root / "merge" / "policy.yaml").read_text() == unchanged


def test_a_proof_short_of_the_bar_is_refused_and_the_file_left_alone(root):
    path = root / "merge" / "pending-proofs.yaml"
    proofs = files.pending_proofs(root)
    proofs[RULE]["correct"] = proofs[RULE]["n"] - 30
    path.write_text(files.dumps(proofs))
    unchanged = (root / "merge" / "policy.yaml").read_text()
    with pytest.raises(Conflict):
        files.approve_rule(RULE, by="Operator", words="yes", at=AT, root=root)
    assert (root / "merge" / "policy.yaml").read_text() == unchanged


def test_the_command_switches_one_rule_on(root, capsys):
    import argparse
    parser = argparse.ArgumentParser()
    register(parser.add_subparsers())
    args = parser.parse_args(["rules", "approve", "--merge", "platform", "--rule", RULE, "--by", "Operator",
                              "--words", "yes", "--root", str(root)])
    assert args.handler(args) == 0
    assert RULE in capsys.readouterr().out
    assert args.handler(args) == 1
    assert "already switched on" in capsys.readouterr().err
