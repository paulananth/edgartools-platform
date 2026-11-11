"""Run files the store decides are declared with a method, a purpose and a why, and built on every load (ticket 202)."""
import pytest

from edgar_warehouse.bookkeeping.clean.config import Blocked, run_inputs
from edgar_warehouse.rules import derivations
from edgar_warehouse.rules.files import source


def target(**derived):
    return {"run": {"facts": [], "files": ["scope", "listing"], "derived": derived}}


HOW = {"method": "lei_scope", "purpose": "The LEIs this load masters.", "why": "A finder never creates a Company."}


def test_a_derived_file_carries_its_method_purpose_and_why():
    assert run_inputs(target(scope=HOW))["derived"] == {"scope": HOW}


@pytest.mark.parametrize("bad", [
    {"nothing": HOW},                                              # not a declared file
    {"scope": {"method": "lei_scope", "purpose": "x"}},            # no why
    {"scope": {**HOW, "why": " "}},                                # an empty why
    {"scope": {**HOW, "method": "Not A Name"}},                    # not a method name
    {"scope": {**HOW, "extra": "x"}},                              # an unknown part
])
def test_a_derived_file_without_its_purpose_and_why_is_refused(bad):
    with pytest.raises(Blocked, match="derived run file"):
        run_inputs(target(**bad))


def test_the_gleif_scope_files_are_derived_with_their_reasons():
    derived = run_inputs(source("gleif")["bookkeeping"]["targets"]["mastering"])["derived"]

    assert {name: how["method"] for name, how in derived.items()} == {
        "approved_scope": "lei_scope", "nport_issuers": "none_flagged"}
    assert all(how["purpose"].strip() and how["why"].strip() for how in derived.values())


def test_every_method_a_rule_names_is_registered():
    for name in ("gleif",):
        for chosen in source(name)["bookkeeping"]["targets"].values():
            for how in run_inputs(chosen)["derived"].values():
                assert how["method"] in derivations.METHODS


def test_an_unknown_method_is_refused(tmp_path):
    with pytest.raises(ValueError, match="No derivation named"):
        derivations.derive("nothing", "scope", folder=tmp_path, store=None)
