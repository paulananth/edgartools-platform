"""The processing identity holds the part of the merge policy that acts on the source (operator, 2026-11-10: "Change
journal must work"): a rule change for another source must not process OpenFIGI's files again. Under the real rules."""

import copy

from edgar_warehouse.control_contract import digest, source_policy_digest
from edgar_warehouse.rules import files

OPENFIGI, NPORT, THIRTEENF = "openfigi.security.v4", "sec.nport.security.v2", "sec.thirteenf.securities.v2"


def rules(policy, kind, source):
    return [r for r in policy["kinds"][kind]["rules"] if r["source"] == source]


def test_the_whole_policy_digest_moves_with_any_rule_but_the_openfigi_slice_does_not():
    policy = files.policy()
    changed = copy.deepcopy(policy)
    rules(changed, "security", NPORT)[0]["version"] = "2099-01-01.test"
    assert digest(changed) != digest(policy)  # what the identity used to be: every rule change reprocessed everything
    assert source_policy_digest(changed, OPENFIGI) == source_policy_digest(policy, OPENFIGI)
    assert source_policy_digest(changed, NPORT) != source_policy_digest(policy, NPORT)


def test_a_company_rule_does_not_move_a_security_source_and_a_security_source_has_its_own_rules():
    policy = files.policy()
    changed = copy.deepcopy(policy)
    changed["kinds"]["company"]["rules"][0]["version"] = "2099-01-01.test"
    assert source_policy_digest(changed, OPENFIGI) == source_policy_digest(policy, OPENFIGI)
    own = copy.deepcopy(policy)
    rules(own, "security", OPENFIGI)[0]["version"] = "2099-01-01.test"
    assert source_policy_digest(own, OPENFIGI) != source_policy_digest(policy, OPENFIGI)
    assert source_policy_digest(own, THIRTEENF) == source_policy_digest(policy, THIRTEENF)


def test_the_identifier_contract_a_source_searches_moves_its_slice_and_one_it_does_not_search_does_not():
    policy = files.policy()
    searched = copy.deepcopy(policy)
    searched["kinds"]["security"]["identifiers"]["cusip"]["claim"]["forward"] = 99  # OpenFIGI searches the CUSIP
    assert source_policy_digest(searched, OPENFIGI) != source_policy_digest(policy, OPENFIGI)
    other = copy.deepcopy(policy)
    other["kinds"]["security"]["identifiers"]["sedol"]["claim"]["forward"] = 99  # only N-PORT searches the SEDOL
    assert source_policy_digest(other, OPENFIGI) == source_policy_digest(policy, OPENFIGI)
    assert source_policy_digest(other, NPORT) != source_policy_digest(policy, NPORT)
