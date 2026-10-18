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
    """A copy of the rules before the name rules were switched on (company
    mastering ticket 25): `approve_rule` appended them, with a comment first."""
    shutil.copytree(files.ROOT, tmp_path / "rules")
    path = tmp_path / "rules" / "merge" / "policy.yaml"
    text = path.read_text()
    marker = f"# {RULE}: switched on by"
    if marker in text:
        path.write_text(text[:text.index(marker)])
    assert not any(e["rule_id"] == RULE for e in files.policy(tmp_path / "rules")["automatic_rules"])
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
    wrong = parser.parse_args(["rules", "approve", "--merge", "platform", "--rule", RULE, "--version", "2",
                               "--by", "Operator", "--words", "yes", "--root", str(root)])
    assert wrong.handler(wrong) == 2


# Rebuild priorities ticket 16, item 14: an identifier matching rule, switched on by command.
IDENTIFIER_RULE = "openfigi-security-isin"


@pytest.fixture
def identifier_root(tmp_path):
    """A copy of the rules with the identifier rule off and the ISIN contract not yet verified."""
    shutil.copytree(files.ROOT, tmp_path / "rules")
    root = tmp_path / "rules"
    path = root / "merge" / "policy.yaml"
    body = files.policy(root)
    kind = root / "merge" / "kinds" / "security.yaml"
    text = kind.read_text()
    contract = body["kinds"]["security"]["identifiers"]["isin"]
    if contract.get("verification"):  # take the stamp out, as it stood before ticket 79
        start = text.index("  isin:\n")
        block_start = text.index("    verification:\n", start)
        block_end = text.index("    tolerance:", block_start)
        kind.write_text(text[:block_start] + text[block_end:])
        # Every rule that activates on the ISIN contract goes with its verification.
        rules = {r["rule_id"] for r in body["kinds"]["security"]["rules"]
                 if any(s.get("args", {}).get("namespace") == "isin" for s in r.get("when") or [])}
        kept, lines, skip = [], path.read_text().split("\n"), 0
        for i, line in enumerate(lines):
            if skip:
                skip -= 1
                continue
            if line.startswith("- kind: security") and any(f"rule_id: {r}" == lines[i + 2].strip() for r in rules):
                skip = 5
                continue
            kept.append(line)
        path.write_text("\n".join(kept))
    after = files.policy(root)
    assert not after["kinds"]["security"]["identifiers"]["isin"].get("verification")
    assert not any(e["rule_id"] == IDENTIFIER_RULE for e in after["automatic_rules"])
    report = tmp_path / "proving-run.json"
    report.write_text('{"isins_on_two_securities": 0}')
    return root, report


def test_an_identifier_rule_is_switched_on_with_its_proving_run(identifier_root):
    import hashlib

    root, report = identifier_root
    kind_before = (root / "merge" / "kinds" / "security.yaml").read_text()
    policy_before = (root / "merge" / "policy.yaml").read_text()
    entry = files.approve_identifier_rule(IDENTIFIER_RULE, proof=report, reason="12 ISINs, 0 on two Securities",
                                          by="Operator", words="Switch it on", at=AT, root=root)
    digest = hashlib.sha256(report.read_bytes()).hexdigest()
    body = files.policy(root)
    assert body["automatic_rules"][-1] == {k: entry[k] for k in ("kind", "family", "rule_id", "rule_version",
                                                                 "verdict", "activation")}
    assert entry["activation"] == "deterministic" and entry["contract_verified_here"]
    assert body["kinds"]["security"]["identifiers"]["isin"]["verification"] == {
        "corpus_sha256": digest, "approved_by": "Operator", "approved_at": AT,
        "reason": "12 ISINs, 0 on two Securities, approved in their words: Switch it on"}
    check_policy(body)
    rule = next(r for r in body["kinds"]["security"]["rules"] if r["rule_id"] == IDENTIFIER_RULE)
    assert activated(body, "security", rule, "bind")
    after = (root / "merge" / "policy.yaml").read_text()
    assert after.startswith(policy_before.rstrip("\n")) and digest in after  # comments kept, report named
    assert f"# {IDENTIFIER_RULE}: switched on by Operator, 2026-09-29 19:30 ET" in after  # the words' time, in ET
    kept = [line for line in kind_before.split("\n") if line.lstrip().startswith("#")]
    assert all(line in (root / "merge" / "kinds" / "security.yaml").read_text() for line in kept)
    with pytest.raises(files.RulesFileError, match="already switched on"):
        files.approve_identifier_rule(IDENTIFIER_RULE, proof=report, reason="r", by="Operator", words="again",
                                      at=AT, root=root)


def test_an_identifier_rule_needs_its_report_and_a_contract_verified_once(identifier_root, tmp_path):
    root, report = identifier_root
    unchanged = {p: p.read_text() for p in ((root / "merge" / "policy.yaml"),
                                            (root / "merge" / "kinds" / "security.yaml"))}
    with pytest.raises(files.RulesFileError, match="not a file"):
        files.approve_identifier_rule(IDENTIFIER_RULE, proof=tmp_path / "none.json", reason="r", by="Operator",
                                      words="yes", at=AT, root=root)
    with pytest.raises(files.RulesFileError, match="does not join on an identifier"):
        files.approve_identifier_rule("sec-gleif-cascade-p1", proof=report, reason="r", by="Operator", words="yes",
                                      at=AT, root=root)
    with pytest.raises(files.RulesFileError, match="exact words"):
        files.approve_identifier_rule(IDENTIFIER_RULE, proof=report, reason="r", by="Operator", words=" ",
                                      at=AT, root=root)
    with pytest.raises(files.RulesFileError, match="declared 0 times"):
        files.approve_identifier_rule("no-such-rule", proof=report, reason="r", by="Operator", words="yes",
                                      at=AT, root=root)
    with pytest.raises(files.RulesFileError, match="--reason"):
        files.approve_identifier_rule(IDENTIFIER_RULE, proof=report, reason=" ", by="Operator", words="yes",
                                      at=AT, root=root)
    assert {p: p.read_text() for p in unchanged} == unchanged


def test_the_command_switches_an_identifier_rule_on(identifier_root, capsys):
    import argparse

    root, report = identifier_root
    parser = argparse.ArgumentParser()
    register(parser.add_subparsers())
    args = parser.parse_args(["rules", "approve", "--merge", "platform", "--rule", IDENTIFIER_RULE,
                              "--proof", str(report), "--reason", "0 on two", "--by", "Operator",
                              "--words", "Switch it on", "--at", "2026-10-18T17:22:00Z", "--root", str(root)])
    assert args.handler(args) == 0
    assert "2026-10-18 13:22 ET" in (root / "merge" / "policy.yaml").read_text()
    assert IDENTIFIER_RULE in capsys.readouterr().out
    assert files.policy(root)["automatic_rules"][-1]["rule_id"] == IDENTIFIER_RULE


def test_a_contract_already_verified_keeps_its_stamp(identifier_root):
    root, report = identifier_root
    first = files.approve_identifier_rule(IDENTIFIER_RULE, proof=report, reason="0 on two", by="Operator",
                                          words="Switch it on", at=AT, root=root)
    stamp = files.policy(root)["kinds"]["security"]["identifiers"]["isin"]["verification"]
    # Take the rule off again; a second switch-on on another report leaves the contract's stamp alone.
    path = root / "merge" / "policy.yaml"
    text = path.read_text()
    path.write_text(text[:text.index(f"# {IDENTIFIER_RULE}: switched on by")])
    other = report.with_name("other-run.json")
    other.write_text('{"isins_on_two_securities": 0, "run": 2}')
    second = files.approve_identifier_rule(IDENTIFIER_RULE, proof=other, reason="0 on two", by="Operator",
                                           words="Again", at=AT, root=root)
    assert first["contract_verified_here"] and not second["contract_verified_here"]
    assert files.policy(root)["kinds"]["security"]["identifiers"]["isin"]["verification"] == stamp
    assert second["proof_sha256"] in path.read_text()


def test_a_failed_switch_on_leaves_both_files_as_they_were(identifier_root, monkeypatch):
    root, report = identifier_root
    files_before = {p: p.read_text() for p in ((root / "merge" / "policy.yaml"),
                                               (root / "merge" / "kinds" / "security.yaml"))}
    real = files.policy
    calls = []

    def broken(where=None):  # the read-back after writing fails
        calls.append(where)
        if len(calls) > 1:
            raise files.RulesFileError("read back failed")
        return real(where)

    monkeypatch.setattr(files, "policy", broken)
    with pytest.raises(files.RulesFileError, match="read back failed"):
        files.approve_identifier_rule(IDENTIFIER_RULE, proof=report, reason="r", by="Operator", words="yes",
                                      at=AT, root=root)
    assert {p: p.read_text() for p in files_before} == files_before
