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
# Company mastering ticket 22 added each feed's quality rule to its contract:
# a new mapping version. Without its `quality` the contract is the one above.
WITH_QUALITY = {
    "contract": "131452e314d1cc892b7bb895235ea60fcd180b55d86b668bde6e2823978d1c28",
    "level1": "58aa14d8a69d06c2ebdd52ea555d5f9bc972bb16c846cc44fdba1e9ead9c4cfd",
}


def _without_quality(contract: dict) -> dict:
    return {k: v for k, v in contract.items() if k != "quality"}


GLEIF_BEFORE = {
    "level1": "0978006ab17593a7f66b5e5b8a6110ff7890aca53f1544b1758bd14dcd8480ef",
    "relationships": "a5a253a8c697bfaf9980bfc995caba260b10b182a103772b61849a7480859136",
    "reporting_exceptions": "963caacea2c6360c9853652e53e6617660e8d7b8eaf3f5d9d2b947d55b0d963f",
}


def test_the_company_configuration_is_unchanged():
    # Rules skill ticket 08 added the SEC place-code table to the policy body;
    # without it the policy is the one that moved here.
    assert digest(company_source.POLICY) == WITH_PLACE_CODES["policy"]
    assert digest({k: v for k, v in company_source.POLICY.items() if k != "reference"}) == (
        BEFORE["policy"]
    )
    assert digest(_without_quality(company_source.CONTRACT)) == BEFORE["contract"]
    assert digest(company_source.CONTRACT) == WITH_QUALITY["contract"]
    assert digest(company_source.FIELDS) == BEFORE["fields"]
    assert digest(company_source.PROOF) == BEFORE["proof"]
    assert digest(company_source.APPROVED_ACTIVATION) == BEFORE["approved_activation"]
    assert digest(company_source.NAME_PROOFS) == BEFORE["name_proofs"]
    assert digest(company_source.name_matching_policy(active=False)) == WITH_PLACE_CODES["policy"]
    assert (
        digest(company_source.name_matching_policy(active=True))
        == WITH_PLACE_CODES["name_matching_active"]
    )


@pytest.mark.parametrize("member", sorted(GLEIF_BEFORE))
def test_each_gleif_mapping_is_unchanged(member):
    contract = gleif_source.dataset_contract(member)
    assert digest(_without_quality(contract)) == GLEIF_BEFORE[member]
    assert digest(contract) == WITH_QUALITY.get(member, GLEIF_BEFORE[member])


def test_a_gleif_relationship_points_at_the_level1_source_it_is_given():
    contract = gleif_source.dataset_contract("relationships", level1_source="x.level1")
    assert [r["target_source"] for r in contract["adapter"]["relationships"]] == ["x.level1"]
    # A fresh copy each call: the substitution never leaks into the next caller.
    assert digest(gleif_source.dataset_contract("relationships")) == GLEIF_BEFORE["relationships"]


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
