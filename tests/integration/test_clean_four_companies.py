"""Real PG16: Apple, Microsoft, Shell and ASML from SEC and GLEIF, into the Stage.

The operator picked these four (company mastering ticket 03, 2026-09-24).
Every input is real: SEC rows are built by the warehouse's own
`stage_company_loader` from retained bronze submissions, and GLEIF rows are
the four Level 1 records from the pinned 2026-09-11 golden copy
(`tests/fixtures/clean_mdm/four_companies_v1/build.py` names every object and
hash). Two individual filers ride along as controls.

What this proves, per record: which kind it was given, by which rule, version
and step, and whether that verdict acted or waited for a Steward.

What it does **not** prove, stated so no reader mistakes it:

- **One Company from both sources.** No binding rule exists yet, so every
  record waits in the Stage and **no master record is created**; SEC Apple and
  GLEIF Apple are two Stage rows, not one Company. Joining them is tickets 04
  and 08 (operator, 2026-09-24: an unlinked record waits in the Stage).
- **That the candidate rule is accurate.** Its activation below carries a
  fixture proof whose arithmetic holds; it measured nothing. A real activation
  needs the Proving Run (ticket 05) and the operator's approval (ticket 06).
- **Production reach.** The warehouse marks every SEC `entityType: "other"`
  filer `non_company` and skips its Company row
  (`is_reporting_company_entity_type`), so production never hands Shell or
  ASML to this adapter. This test builds their rows directly from bronze.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text

from edgar_warehouse.mdm.clean.bookkeeping import RunCoordinator
from edgar_warehouse.mdm.clean.cli import batch_evidence, execute_manifest
from edgar_warehouse.mdm.clean.company_source import CONTRACT, POLICY, SOURCE_CODE
from edgar_warehouse.mdm.clean.source_publications import PublicationVerifier
from edgar_warehouse.mdm.clean.store import Store, register_dataset, register_policy
from tests.integration import test_clean_mdm_postgres as core
from tests.integration import test_clean_native_publications as native
from tests.integration import test_clean_source_publications as sources
from tests.mdm.test_clean_activation import BAR, proof

postgres = core.postgres
database = core.database
command_databases = core.command_databases
acquisition_login = sources.acquisition_login
source_db = sources.source_db

FIXTURE = json.loads(
    (
        Path(__file__).parents[1]
        / "fixtures/clean_mdm/four_companies_v1/four_companies_v1.json"
    ).read_text()
)
APPLE, MICROSOFT, SHELL, ASML = "0000320193", "0000789019", "0001306965", "0000937966"
COOK, NADELLA = "0001214156", "0001513142"
COMPANIES = {APPLE, MICROSOFT, SHELL, ASML}

# A candidate, not a measured rule. Step 2 is the one the lookup table lacks:
# SEC says "other" for a foreign issuer and for an individual alike, and only
# the issuer carries an industry code.
RULE = {
    "rule_id": "sec-company-candidate",
    "version": "2026-09-24",
    "family": "classification",
    "emits": ["company", "deferred"],
    "steps": [
        {
            "step": "1",
            "verdict": "company",
            "when": [
                {
                    "primitive": "field_in_set@1",
                    "args": {
                        "field": "entity_type",
                        "values": ["operating", "investment"],
                    },
                }
            ],
        },
        {
            "step": "2",
            "verdict": "company",
            "when": [
                {
                    "primitive": "field_in_set@1",
                    "args": {"field": "entity_type", "values": ["other"]},
                },
                {"primitive": "evidence_present@1", "args": {"document": "sic"}},
            ],
        },
        {"step": "3", "verdict": "deferred", "otherwise": True},
    ],
}
NAMED = {"kind": "company", "rule_id": RULE["rule_id"], "version": RULE["version"]}


def rule_contract():
    contract = copy.deepcopy({**CONTRACT, "family": "fixture"})
    del contract["adapter"]["kind_field"], contract["adapter"]["kind_values"]
    contract["adapter"]["classification"] = NAMED
    return contract


def rule_policy(*, active):
    body = copy.deepcopy(POLICY)
    body["version"] = "four-companies-test"
    body["kinds"]["company"].update(rules=[RULE], bars={"classification": BAR})
    if active:
        body["automatic_rules"] = [
            {
                "kind": "company",
                "family": "classification",
                "rule_id": RULE["rule_id"],
                "rule_version": RULE["version"],
                "verdict": "company",
                "activation": "measured",
                "proof": proof(),
            }
        ]
    return body


def sec_batch(tmp_path):
    raw = (
        "\n".join(json.dumps(row, sort_keys=True) for row in FIXTURE["sec"]) + "\n"
    ).encode()
    (tmp_path / "sec.jsonl").write_bytes(raw)
    return {
        "batch_id": "sec-four-companies",
        "stage": "mastering",
        "consumer": "sec-company",
        "expected_checkpoint": 0,
        "checkpoint": 1,
        "input": {
            "path": "sec.jsonl",
            "sha256": hashlib.sha256(raw).hexdigest(),
            "source_code": SOURCE_CODE,
            "record_count": len(FIXTURE["sec"]),
            "publication": {
                "publication_key": "bronze-fixture",
                "revision": 0,
                "effective_at": None,
            },
        },
    }


def register(database, contract, policy):
    with database.admin.begin() as conn:
        register_dataset(conn, SOURCE_CODE, database.registry, contract)
        return register_policy(conn, policy)


def by_record(evidence, deferred):
    kinds = {a["record_key"]: a for a in evidence}
    for record in deferred:
        cik = str(record["raw_record"]["cik"]).zfill(10)
        kinds[cik] = record
    return kinds


def stage_and_master(database):
    with database.application.connect() as conn:
        stage = conn.execute(
            text("SELECT source_code, record_key FROM mdm_v2.company_stage")
        ).all()
        masters = conn.scalar(text("SELECT count(*) FROM mdm_v2.company_master"))
    return sorted(stage), masters


def test_todays_lookup_table_turns_shell_and_asml_away(database, tmp_path):
    """The baseline: SEC's `entityType` alone decides, so foreign issuers fail."""
    policy = register(database, {**CONTRACT, "family": "fixture"}, POLICY)
    evidence, deferred = batch_evidence(
        sec_batch(tmp_path), tmp_path, Store(database.application), policy_digest=policy
    )
    records = by_record(evidence, deferred)
    assert {k for k, r in records.items() if r.get("kind") == "company"} == {
        APPLE,
        MICROSOFT,
    }
    for cik in (SHELL, ASML, COOK, NADELLA):
        assert records[cik]["reason"] == "unsupported_identity_kind"


def test_the_rule_names_all_four_companies_but_acts_on_none_unactivated(
    database, tmp_path
):
    """Declared, not active: every verdict waits for a Steward, with its rule."""
    policy = register(database, rule_contract(), rule_policy(active=False))
    evidence, deferred = batch_evidence(
        sec_batch(tmp_path), tmp_path, Store(database.application), policy_digest=policy
    )
    assert evidence == []
    records = by_record(evidence, deferred)
    for cik, step in ((APPLE, "1"), (MICROSOFT, "1"), (SHELL, "2"), (ASML, "2")):
        assert records[cik]["reason"] == "classification_not_activated"
        assert records[cik]["provenance"]["classification"] == {
            "rule_id": "sec-company-candidate",
            "version": "2026-09-24",
            "step": step,
            "verdict": "company",
        }
    for cik in (COOK, NADELLA):
        assert records[cik]["reason"] == "classification_deferred"
        assert records[cik]["provenance"]["classification"]["step"] == "3"


def test_both_sources_wait_in_the_stage_and_no_master_is_created(
    database, source_db, command_databases, tmp_path
):
    """Activated: four SEC Companies and four GLEIF Companies, eight Stage rows.

    No binding rule exists, so nothing reaches `company_master`: this is the
    operator's rule that an unlinked record waits in the Stage, not a failure.
    """
    policy = register(database, rule_contract(), rule_policy(active=True))
    store = Store(database.application)
    coordinator = RunCoordinator(command_databases[0], store)
    manifest = tmp_path / "sec-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "contract_version": 2,
                "policy_digest": policy,
                "as_of": core.AS_OF,
                "batches": [sec_batch(tmp_path)],
            }
        )
    )
    sec = execute_manifest(
        store,
        coordinator,
        path=str(manifest),
        run_id=str(uuid4()),
        stage="mastering",
        limit=len(FIXTURE["sec"]),
    )
    assert sec["records_processed"] == 6
    with database.application.connect() as conn:
        labelled = dict(
            conn.execute(
                text(
                    "SELECT record_key, body->'provenance'->'classification'->>'step' "
                    "FROM mdm_v2.company_stage"
                )
            ).all()
        )
        set_aside = conn.execute(
            text(
                "SELECT body->'raw_record'->>'cik', body->>'reason', "
                "body->'provenance'->'classification'->>'step' "
                "FROM mdm_v2.deferred_record"
            )
        ).all()
        assert sorted(set_aside) == [
            ("1214156", "classification_deferred", "3"),
            ("1513142", "classification_deferred", "3"),
        ]
    assert labelled == {APPLE: "1", MICROSOFT: "1", SHELL: "2", ASML: "2"}

    gleif = FIXTURE["gleif"]
    capture, path = native.native_fixture(
        database,
        source_db,
        tmp_path,
        level1=gleif[0],
        additional_level1=gleif[1:],
        company_leis=[r["LEI"]["$"] for r in gleif],
        policy=policy,
    )
    result = execute_manifest(
        store,
        coordinator,
        path=str(path),
        run_id=str(uuid4()),
        stage="mastering",
        limit=6,
        publication_verifier=PublicationVerifier(source_db, capture.reader),
    )
    assert result["source_consumption_complete"] is True

    stage, masters = stage_and_master(database)
    assert stage == sorted(
        [(SOURCE_CODE, cik) for cik in COMPANIES]
        + [("gleif.level1.v1", r["LEI"]["$"]) for r in gleif]
    )
    assert masters == 0


# The SEC and GLEIF record of each Company. The pairs are **test input**, picked
# by the operator: no matching rule links them yet (tickets 04 and 08). They
# stand in for that rule so the master row can be shown.
PAIRS = {
    APPLE: "HWUPKR0MPOU8FGXBT394",
    MICROSOFT: "INR2EJN1ERAN0W5ZP974",
    SHELL: "21380068P1DRHMJ8KU70",
    ASML: "724500Y6DUVHQD6OXN27",
}


def test_one_master_per_company_takes_fields_from_both_sources(
    database, source_db, command_databases, tmp_path, capsys
):
    """The Company rule: every field from every source, SEC first where both.

    Operator, 2026-09-24: name and jurisdiction are one field each; SEC wins
    when both supply one and GLEIF's value is kept as a retained conflict;
    jurisdiction is compared in one format (SEC "CA" is GLEIF "US-CA"); a
    field only one source has comes from that source.
    """
    from edgar_warehouse.mdm.clean.evidence import decision
    from edgar_warehouse.mdm.clean.merge import MergeStage

    policy = register(database, rule_contract(), rule_policy(active=True))
    store = Store(database.application)
    coordinator = RunCoordinator(command_databases[0], store)
    manifest = tmp_path / "sec-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "contract_version": 2,
                "policy_digest": policy,
                "as_of": core.AS_OF,
                "batches": [sec_batch(tmp_path)],
            }
        )
    )
    execute_manifest(
        store,
        coordinator,
        path=str(manifest),
        run_id=str(uuid4()),
        stage="mastering",
        limit=6,
    )
    gleif = FIXTURE["gleif"]
    capture, path = native.native_fixture(
        database,
        source_db,
        tmp_path,
        level1=gleif[0],
        additional_level1=gleif[1:],
        company_leis=[r["LEI"]["$"] for r in gleif],
        policy=policy,
    )
    execute_manifest(
        store,
        coordinator,
        path=str(path),
        run_id=str(uuid4()),
        stage="mastering",
        limit=6,
        publication_verifier=PublicationVerifier(source_db, capture.reader),
    )
    with database.application.connect() as conn:
        stored = {
            r[0]: r[1]
            for r in conn.execute(
                text("SELECT body->>'record_key', body FROM mdm_v2.assertion")
            )
        }
    identities, decisions, entity_of = [], [], {}
    for cik, lei in PAIRS.items():
        entity_id = str(uuid4())
        entity_of[cik] = entity_id
        identities.append(
            {"entity_id": entity_id, "kind": "company", "published_at": core.AT}
        )
        for key in (cik, lei):
            decisions.append(
                decision(
                    "bind",
                    actor="test",
                    reason="operator-picked pair; stands in for tickets 04 and 08",
                    at=core.AT,
                    subject=stored[key]["subject"],
                    entity_id=entity_id,
                    evidence=[stored[key]["assertion_id"]],
                )
            )
    MergeStage(store).apply(
        batch_id="link-four-companies",
        run_id=str(uuid4()),
        policy_digest=policy,
        consumer="link-test",
        expected_checkpoint=0,
        checkpoint=1,
        as_of=core.AS_OF,
        identities=identities,
        decisions=decisions,
    )
    masters = core.documents(database, "entity")
    assert len(masters) == 4

    def field(cik, name):
        return masters[entity_of[cik]]["fields"].get(name)

    def winner(cik, name):
        return field(cik, name)["winner"]["source_code"]

    for cik, lei in PAIRS.items():
        assert masters[entity_of[cik]]["identifiers"] == {"cik": [cik], "lei": [lei]}
        # Both sources supply a name: SEC wins.
        assert winner(cik, "name") == SOURCE_CODE
        # Only SEC has SIC; only GLEIF has legal form and registration status.
        assert winner(cik, "sic") == SOURCE_CODE
        assert winner(cik, "gleif_legal_form") == "gleif.level1.v1"
        assert field(cik, "gleif_registration_status")["value"] == "ISSUED"
    # GLEIF spells Apple exactly as SEC does, so there is nothing to keep;
    # where the two spell it differently, GLEIF's spelling is kept as a
    # conflict beside SEC's winning value.
    assert field(APPLE, "name")["value"] == "Apple Inc."
    assert field(APPLE, "name")["conflicts"] == []
    assert field(MICROSOFT, "name")["value"] == "MICROSOFT CORP"
    assert [c["value"] for c in field(MICROSOFT, "name")["conflicts"]] == [
        "MICROSOFT CORPORATION"
    ]
    # One format: SEC "CA" and GLEIF "US-CA" agree, so no conflict is kept.
    assert field(APPLE, "jurisdiction")["value"] == "US-CA"
    assert field(APPLE, "jurisdiction")["conflicts"] == []
    assert field(MICROSOFT, "jurisdiction")["value"] == "US-WA"
    # ASML: SEC states no jurisdiction, so GLEIF's fills the field.
    assert field(ASML, "jurisdiction")["value"] == "NL"
    assert winner(ASML, "jurisdiction") == "gleif.level1.v1"
    # Shell: SEC says "DC" (a US code) and wins; GLEIF's "GB" is kept as a
    # conflict. SEC-first is the rule as decided; this is where it bites.
    assert field(SHELL, "jurisdiction")["value"] == "US-DC"
    assert [c["value"] for c in field(SHELL, "jurisdiction")["conflicts"]] == ["GB"]

    # GLEIF's own spelling is still in the Stage, whole, as evidence.
    with database.application.connect() as conn:
        staged = conn.execute(
            text(
                "SELECT body->'fields'->'name'->>'value' FROM mdm_v2.company_stage "
                "WHERE source_code='gleif.level1.v1' AND record_key=:lei"
            ),
            {"lei": PAIRS[MICROSOFT]},
        ).scalar_one()
    assert staged == "MICROSOFT CORPORATION"
    # SEC's raw state code survives beside the converted jurisdiction.
    assert field(SHELL, "sec_state_of_incorporation")["value"] == "DC"

    with capsys.disabled():
        print()
        for cik in PAIRS:
            row = masters[entity_of[cik]]
            print(
                f"--- {field(cik, 'name')['value']}  identifiers={row['identifiers']}"
            )
            for name in sorted(row["fields"]):
                f = row["fields"][name]
                others = [
                    f"{c['source_code']}={c.get('value')!r}" for c in f["conflicts"]
                ]
                print(
                    f"  {name:40} {f.get('value')!r:40} from {f['winner']['source_code']}"
                    + (f"   kept: {', '.join(others)}" if others else "")
                )


def test_a_contract_naming_an_unknown_field_format_is_refused(database):
    contract = copy.deepcopy({**CONTRACT, "family": "fixture"})
    contract["adapter"]["field_formats"] = {"jurisdiction": "invented"}
    with database.admin.begin() as conn, pytest.raises(ValueError, match="format"):
        register_dataset(conn, SOURCE_CODE, database.registry, contract)
    contract["adapter"]["field_formats"] = {"unmapped": "edgar_state_iso3166"}
    with (
        database.admin.begin() as conn,
        pytest.raises(ValueError, match="does not map"),
    ):
        register_dataset(conn, SOURCE_CODE, database.registry, contract)
