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
# Company's policy layers and their digests, newest first, are in
# `tests/mdm/policy_layers.py` (`LAYERS`, `PINNED`): one place for each.

# Company mastering ticket 22 added each feed's quality rule to its contract,
# with its exceptions listed as non-blocking: a new mapping version. Without
# both the contract is the one above.
WITH_QUALITY = {
    "contract": "37b6634c515a6f0747c06ab1ab09e7b2cba87ce61fc2ad54eb73838d1dc84dcc",
    "level1": "fb4a2d7d3529d02c38829d4c44c1d67756ea505479fcccca7a7e99d7e215f28e",
}


def _with_yaml_place_check(contract: dict) -> dict:
    """The place-code check as it was: pinned to `rules/reference/sec-place-codes.yaml`
    by that file's sha256, its keys under `codes`."""
    checks = [{**c, "args": {**c["args"], "sha256": "5a5a504286180523272d74fbbdc35078bb636bd4343309637041970c3e803a12",
                             "key": "codes"}} if c["id"] == "state_code_known" else c
              for c in contract["quality"]["checks"]]
    return {**contract, "quality": {**contract["quality"], "checks": checks}}


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
# Profiling ticket 02 (handoff C3): the place-code check reads the published
# RDM version the policy pins; without that, the check pins the removed YAML
# and the contract is the one below.
WITH_PINNED_PLACE_CHECK = "472295c9222ac017ceeac3705693ea9ca94ebdcb151a78c8cc56e1f2bd39e7ba"
SEC_CONFIGURED_FIELDS = {
    "sec.submissions.company": "f01b9d7077376cc4adc3a5bae8f82a294992ed76c7f729d58b5f43198ed1259e",
    "sec.submissions.person": "9ab5f191e7f18f58c1be5cedda3841d86c577f6074f9904a14c4f3eb1d875605",
}
PERSON_BEFORE_CONFIGURED_FIELDS = "a740357f911d531ae72a995409d5630b1eeced83c5c8b8078f5d806d8563dd9a"


def test_the_company_configuration_is_unchanged():
    # Rules skill ticket 08 added the SEC place-code table to the policy body;
    # without it the policy is the one that moved here.
    assert policy_layers.digests(COMPANY) == policy_layers.PINNED
    assert policy_layers.PINNED[-1] == BEFORE["policy"]
    # Ticket 18 made the SEC reading v7 (a region only for a state or
    # province; each ticker once); with v6 the contract is the one before.
    assert digest(company_source.CONTRACT) == WITH_PINNED_PLACE_CHECK
    assert digest(_with_yaml_place_check(company_source.CONTRACT)) == SEC_CONFIGURED_FIELDS["sec.submissions.company"]
    contract = _without_configured_reading(_with_yaml_place_check(company_source.CONTRACT))
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
