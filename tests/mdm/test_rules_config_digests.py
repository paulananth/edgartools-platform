"""Moving the Clean MDM configuration into `rules/` changed no digest.

Each digest below was taken from the Python and JSON copies before they moved
(rules skill ticket 01, 2026-09-26). A digest that moves means Clean MDM would
register different rules: the live Company policy is `983352e8…4049`.
"""

from __future__ import annotations


import pytest

from edgar_warehouse.mdm.clean import company_source, gleif_source
from edgar_warehouse.mdm.clean.store import canonical, digest
from edgar_warehouse.rules import files
from tests.mdm import policy_layers

BEFORE = {
    "policy": "983352e81d295a165a1391e82fa8a24a710e6f638361a577f18f541917fd4049",
    "contract": "6d833bebb781a1a0c8e1f288ac53787be8fd1d6f9ce9a4d3d7294bf8b44907d3",
    "fields": "8674b4d197d012e09b0b9680fe28a208b8b0ab44aa688d1bee6ebd1e93a2af3a",
    "proof": "7c46a44386fe307576685efdc81666188619a40c91c6150c2ba824c30aad155c",
    "approved_activation": "bb2758761a014f5f7e9524ae5a3da261b5346527618467e843732ed86a10a0a8",
    "name_proofs": "42e7b849964f64d17eaf35ae2e9f02c46ee8783501ac87e8206e65eb031be6ef",
    "name_matching_active": "c21dc69cdf1f2004d28afdacc120ca086c46475621b3709dfcfdc3fad1a6d0fb",
}
WITH_PLACE_CODES = {
    "policy": "3520e890d46020e1c0a579807151b9d1cadcf5adab535172811b8e96f99b1e17",
    "name_matching_active": "ad70680ac2cbeb04da821038436ccd0c5eff8bfa74f96e29cc205bdd0cd8db80",
}
# Company mastering ticket 21 declared the cascade's seven passes, switched
# off; without them the policy is the one above, so the approved rules are
# unchanged (operator, 2026-09-28: they stay until ticket 20).
WITH_CASCADE = {
    "policy": "8bdc2f68294bbe93aebaa1949090073d1bec4f2adb95fddfdc11594344f6555d",
    "name_matching_active": "8bec2b784b140257223fb8faf592290f679c06c223e0803c69adfb2080045583",
}



# Company mastering ticket 15 declared the CIK matching rule and its Identifier
# Contract, switched off; without them the policy is the one above.
WITH_CIK = {
    "policy": "0d4d5cb0f190a4486c7cc65c7ba71b4dc173e3ce82eb2734261caea7c6c20702",
    "name_matching_active": "34f7174cc9cb5b8390e8afc592e2487d0b1e488544f6d908641acd252e598a24",
}


# The operator approved 0d4d5cb0...0702 on 2026-09-29 07:27 ET (ticket 15): the
# contract's stamps are filled and the rule is switched on.
WITH_CIK_APPROVAL = {
    "policy": "15e07b302482bbbe191fd5b89855373f04f18db31a3c9caaa733f1bc87b9b6d6",
    "name_matching_active": "86a7a9e3f9bd9e2bd428331442f031f2b4736f55ee3f890c329de0c05f21acde",
}

# The operator approved switching both name matching rules on ("yes",
# 2026-09-29 21:04 ET, company mastering ticket 25); without them it is the
# policy above.
WITH_NAME_RULES_ON = {
    "policy": "75bd2b6744c075750c5f86632aa7e9fd504be03a648f91a1b0f3ab8c51e33dbe",
}

# Platform validation 06a added GLEIF's relationship file to Company's
# sources, for its accounting-parent links; without it the policy is the one
# above.
WITH_GLEIF_PARENT_LINKS = {
    "policy": "6978715fa0b862e00caecc791c239c5b3ed8ffdf7450521bf761c886a5708ae5",
}

# Profiling ticket 04 moved the relationship types from code into the policy
# (operator, 2026-10-06: "Types as data"); without them the policy is the one
# above. Production keeps the policy above until the operator approves this one.
WITH_RELATIONSHIP_TYPES = {
    "policy": "1e38238fbb48390f13188c52ff312606aead9d942380dac31f0f5a1154203da4",
}

# Profiling ticket 04b names every relationship type as its source or standard
# does (operator, 2026-10-07, each name approved one by one); peeled, the types
# are the table profiling ticket 04 moved into the policy, and the policy is
# the one below.
WITH_REAL_NAMES = {
    "policy": "bf682fa4e2ba378ded491a6d6aa46b2a417682f1de4d5d20adb1490177efb2f6",
}

# Profiling ticket 04b, part B: the calculated ultimate parent keeps its
# history (accounting-chain-v2) and a successor entity ends parent links
# (operator, 2026-10-07: "It should also consider corporate actions"); peeled,
# the policy is the one above.
WITH_PARENT_HISTORY = {
    "policy": "c608d93a9e72f965624ff467321f8aecab4e6cd13074cd1fbda7d6fc82001605",
}

# Profiling ticket 02 pins the reference data (RDM `sec-place-codes` version
# 1 and its sha256) in place of the embedded table; the operator approved it
# ("Ticket 02's last step needs your approval. Approved", 2026-10-07 08:01 ET).
# Peeled, the table is embedded again and the policy is the one above.
WITH_REFERENCE_PINS = {
    "policy": "058759172d1de36cc397ee89aa0c4630c11c86dcc29a4c6d5f42c96b0e4c8ee4",
}

# Company mastering ticket 22 added each feed's quality rule to its contract,
# with its exceptions listed as non-blocking: a new mapping version. Without
# both the contract is the one above.
WITH_QUALITY = {
    "contract": "37b6634c515a6f0747c06ab1ab09e7b2cba87ce61fc2ad54eb73838d1dc84dcc",
    "level1": "fb4a2d7d3529d02c38829d4c44c1d67756ea505479fcccca7a7e99d7e215f28e",
}


def _without_quality(contract: dict) -> dict:
    """The contract without what ticket 22 added: its `quality`, its exception
    reasons, and GLEIF's headquarters address in matching."""
    body = {k: v for k, v in contract.items() if k != "quality"}
    reasons = [r for r in body.get("nonblocking_deferred_reasons", []) if not r.startswith("quality_")]
    body.pop("nonblocking_deferred_reasons", None)
    matching = {k: v for k, v in body["adapter"].get("matching", {}).items() if k != "headquarters_address"}
    body["adapter"] = {**body["adapter"], **({"matching": matching} if "matching" in body["adapter"] else {})}
    return {**body, **({"nonblocking_deferred_reasons": reasons} if reasons else {})}


GLEIF_BEFORE = {
    "level1": "0978006ab17593a7f66b5e5b8a6110ff7890aca53f1544b1758bd14dcd8480ef",
    "relationships": "a5a253a8c697bfaf9980bfc995caba260b10b182a103772b61849a7480859136",
    "reporting_exceptions": "963caacea2c6360c9853652e53e6617660e8d7b8eaf3f5d9d2b947d55b0d963f",
}


# Company's part of the policy: a new kind does not move these pins
# (platform validation 05a).
COMPANY = policy_layers.company_part(company_source.POLICY)

SEC_READING_V7 = "5d9ed22b068f2387a851590e385a7fd4da3447f3fcbea92f73c9c0fba89d9be4"
# Native mapped-value reading requires approval of new source digests. Removing
# only the new reading retains the complete historical contract protection.
SEC_CONFIGURED_FIELDS = {
    "sec.submissions.company": "f01b9d7077376cc4adc3a5bae8f82a294992ed76c7f729d58b5f43198ed1259e",
    "sec.submissions.person": "9ab5f191e7f18f58c1be5cedda3841d86c577f6074f9904a14c4f3eb1d875605",
}
PERSON_BEFORE_CONFIGURED_FIELDS = "a740357f911d531ae72a995409d5630b1eeced83c5c8b8078f5d806d8563dd9a"


def test_the_company_configuration_is_unchanged():
    # Rules skill ticket 08 added the SEC place-code table to the policy body;
    # without it the policy is the one that moved here.
    layered = (WITH_PARENT_HISTORY, WITH_REAL_NAMES, WITH_REFERENCE_PINS, WITH_RELATIONSHIP_TYPES, WITH_GLEIF_PARENT_LINKS, WITH_NAME_RULES_ON, WITH_CIK_APPROVAL, WITH_CIK, WITH_CASCADE, WITH_PLACE_CODES, BEFORE)
    assert policy_layers.digests(COMPANY) == [pins["policy"] for pins in layered]
    # Ticket 18 made the SEC reading v7 (a region only for a state or
    # province; each ticker once); with v6 the contract is the one before.
    assert digest(company_source.CONTRACT) == SEC_CONFIGURED_FIELDS["sec.submissions.company"]
    contract = _without_configured_reading(company_source.CONTRACT)
    assert digest(contract) == SEC_READING_V7
    v6 = {**contract, "adapter": {**contract["adapter"],
                                                  "version": "sec-company-landing-v6"}}
    assert digest(v6) == WITH_QUALITY["contract"]
    assert digest(_without_quality(v6)) == BEFORE["contract"]
    assert digest(company_source.FIELDS) == BEFORE["fields"]
    assert digest(company_source.PROOF) == BEFORE["proof"]
    assert digest(company_source.APPROVED_ACTIVATION) == BEFORE["approved_activation"]
    assert digest(policy_layers.company_proofs(company_source.NAME_PROOFS, COMPANY)) == BEFORE["name_proofs"]
    # Each switched-on name rule carries its measured proof, unchanged, with
    # the operator's approval added.
    for entry in COMPANY["automatic_rules"]:
        if entry["rule_id"] in policy_layers.NAME_RULES:
            stamped = {"approved_by", "approved_at", "approved_words"}
            measured = company_source.NAME_PROOFS[entry["rule_id"]]
            assert {k: v for k, v in entry["proof"].items() if k not in stamped} == {
                k: v for k, v in measured.items() if k not in stamped}
            assert (entry["proof"]["approved_by"], entry["proof"]["approved_words"]) == ("operator", "yes")


# Company mastering ticket 18 listed an invalid LEI as non-blocking in each
# GLEIF contract; without those two reasons each contract is the one above.
WITH_INVALID_LEI = {
    "level1": "74b8b1f4c10bd53b591d17456cb3c33b124d2444ab1245c77ebea8d21a8f11bc",
    "relationships": "586cbbce96744b978bd88a5c9b7842ec50871c30ca0f7d3a42a1989e6b891ccf",
    "reporting_exceptions": "f376c348866eb2dc3720d127ad3e55310a222678ed6eba4374315b66ff92808d",
}


# Platform validation 06a: a GLEIF relationship record's link starts at the
# child's Level 1 record (`source_key`); without it the contract is the one above.
WITH_LINK_START = {
    "relationships": "5e4a23fc22080b1c9c5f04fd66d38eb4ab19f1481c91da0c3a252efe5b361e1b",
}


# Profiling ticket 04c: GLEIF Level 1 states its successor entities (one
# SUCCESSOR_ENTITY link per successor LEI, dated by the completed succession
# event naming it, with the ceased entity's status); without that relationship
# mapping the contract is the one above.
WITH_SUCCESSOR = {
    "level1": "5cbf17245e2b327b4931a4be63ce674f665545cb28b540be3ef8a8dae92746c7",
}


# PR #857 adds frozen native mapped-value reading. The new contract hashes
# require separate operator approval for activation. Peeling only that added
# reading preserves every earlier mapping/quality/relationship digest gate.
WITH_CONFIGURED_READING = {
    "level1": "f53c9c428b65440b18a4567d363c0075d372fa9db1d661dec5b415d974d73ffe",
    "relationships": "b7493a71495dabcde680e31560a0d82393030ab0eb71334d6897ae98b0e0cc2e",
    "reporting_exceptions": "77bb3a8d3e9f9103168946b9e565b9e17264628e1d77923a06ee4cecbe75688d",
}


def _without_configured_reading(contract: dict) -> dict:
    return {**contract, "adapter": {k: v for k, v in contract["adapter"].items() if k != "reading"}}


def _without_successor(contract: dict) -> dict:
    if contract["adapter"]["native_member"] != "level1":
        return contract
    return {**contract, "adapter": {k: v for k, v in contract["adapter"].items() if k != "relationships"}}


def _without_link_start(contract: dict) -> dict:
    adapter = dict(contract["adapter"])
    if adapter.get("relationships"):
        adapter["relationships"] = [
            {k: v for k, v in r.items() if k not in {"source_key", "source_source"}}
            for r in adapter["relationships"]
        ]
    return {**contract, "adapter": adapter}


def _without_invalid_lei(contract: dict) -> dict:
    reasons = [r for r in contract["nonblocking_deferred_reasons"] if r not in {"invalid_lei", "invalid_lei_checksum"}]
    return {**contract, "nonblocking_deferred_reasons": reasons}


@pytest.mark.parametrize("member", sorted(GLEIF_BEFORE))
def test_each_gleif_mapping_is_unchanged(member):
    contract = gleif_source.dataset_contract(member)
    assert digest(contract) == WITH_CONFIGURED_READING[member]
    contract = _without_configured_reading(contract)
    assert digest(contract) == WITH_SUCCESSOR.get(member, WITH_LINK_START.get(member, WITH_INVALID_LEI[member]))
    contract = _without_successor(contract)
    assert digest(contract) == WITH_LINK_START.get(member, WITH_INVALID_LEI[member])
    contract = _without_link_start(contract)
    assert digest(contract) == WITH_INVALID_LEI[member]
    earlier = _without_invalid_lei(contract)
    assert digest(earlier) == WITH_QUALITY.get(member, GLEIF_BEFORE[member])
    assert digest(_without_quality(earlier)) == GLEIF_BEFORE[member]


def test_a_gleif_relationship_points_at_the_level1_source_it_is_given():
    contract = gleif_source.dataset_contract("relationships", level1_source="x.level1")
    assert [r["target_source"] for r in contract["adapter"]["relationships"]] == ["x.level1"]
    assert [r["source_source"] for r in contract["adapter"]["relationships"]] == ["x.level1"]
    # A fresh copy each call: the substitution never leaks into the next caller.
    assert digest(gleif_source.dataset_contract("relationships")) == WITH_CONFIGURED_READING["relationships"]
    assert digest(_without_configured_reading(gleif_source.dataset_contract("relationships"))) == WITH_LINK_START["relationships"]


def test_an_unknown_gleif_member_is_refused():
    with pytest.raises(ValueError, match="Unknown native GLEIF member"):
        gleif_source.dataset_contract("level2")


@pytest.mark.parametrize(
    "path",
    sorted(p.relative_to(files.ROOT).as_posix() for p in files.ROOT.rglob("*.yaml")),
)
def test_every_rules_file_round_trips_exactly(path):
    value = files.load(files.ROOT / path)
    assert canonical(files.loads(files.dumps(value))) == canonical(value)


def test_person_configured_fields_preserve_the_previous_contract_digest():
    contract = files.mdm_contract("sec.submissions.person", "sec.submissions.person.v1")
    assert digest(contract) == SEC_CONFIGURED_FIELDS["sec.submissions.person"]
    assert digest(_without_configured_reading(contract)) == PERSON_BEFORE_CONFIGURED_FIELDS
