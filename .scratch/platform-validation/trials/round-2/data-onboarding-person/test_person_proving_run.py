"""Trial proving run for sec.submissions.person.v1 + person-cik, on a disposable PostgreSQL 16.

TEST INPUTS (not approvals, never saved anywhere):
- the contract's classification is replaced in memory by `kind: person`, and only the 287
  records the in-memory test pass of sec-person-candidate labelled `person` are applied;
- person.yaml's Identifier Contract for cik gets a placeholder `verification`, and person-cik
  is added to automatic_rules as deterministic, in memory only, so the matching rule can run.
"""
import copy, glob, hashlib, json, os, sys
from collections import Counter
from pathlib import Path
from uuid import uuid4
sys.path.insert(0, os.getcwd())
from sqlalchemy import text
from edgar_warehouse.rules import files
from edgar_warehouse.mdm.clean.adapters import normalize, UnsupportedRecord
from edgar_warehouse.mdm.clean.merge import MergeStage
from edgar_warehouse.mdm.clean.store import Store, register_policy
from tests.integration import test_clean_mdm_postgres as core
from tests.support.rules_authority import register_dataset

postgres = core.postgres
database = core.database
W = Path("/Users/aneenaananth/.local/share/edgartools/clean-mdm/trials/person-feed-1/work2")
IN = "/Users/aneenaananth/.local/share/edgartools/clean-mdm/trials/person-feed-1/inputs"
CODE = "sec.submissions.person.v1"
AS_OF = "2026-09-30T12:00:00+00:00"

def inputs():
    contract = copy.deepcopy(files.source("sec.submissions.person", root=W / "rules")["mdm"][CODE]["contract"])
    named = contract["adapter"].pop("classification")
    contract["adapter"]["kind"] = "person"             # TEST INPUT
    policy = files.policy(root=W / "rules")
    policy["kinds"]["person"]["identifiers"]["cik"]["verification"] = {   # TEST INPUT
        "corpus_sha256": "0" * 64, "approved_by": "TEST INPUT (trial, not an approval)",
        "approved_at": "2026-09-30T00:00:00Z", "reason": "trial proving run only"}
    policy["automatic_rules"] = list(policy.get("automatic_rules") or []) + [{
        "kind": "person", "family": "binding", "rule_id": "person-cik",
        "rule_version": "2026-09-30", "verdict": "bind", "activation": "deterministic"}]
    labelled = json.load(open(W / "dry-run-person-members.json"))
    return contract, policy, set(labelled)

def assertions_for(contract, policy, keep):
    out = []
    for f in sorted(glob.glob(IN + "/*.json")):
        m = os.path.basename(f)
        if m not in keep:
            continue
        raw = open(f, "rb").read()
        pub = {"artifact_sha256": hashlib.sha256(raw).hexdigest(), "member": m,
               "publication_key": "trial-person-feed-1", "revision": 0}
        out.append(normalize(json.loads(raw), source_code=CODE, contract=contract, publication=pub, policy=policy))
    return out

def counts(conn):
    group = lambda sql: {str(k): v for k, v in conn.execute(text(sql)).all()}
    return {"identities": group("SELECT kind, count(*) FROM mdm.master_entity GROUP BY kind"),
            "stage_records": group("SELECT source_code||':'||kind, count(*) FROM mdm.stage_record GROUP BY 1"),
            "stage_bound": group("SELECT source_code, count(*) FROM mdm.stage_record WHERE entity_id IS NOT NULL GROUP BY 1"),
            "decisions": group("SELECT operation, count(*) FROM mdm.decision GROUP BY 1"),
            "ciks_on_two_persons": conn.execute(text(
                "SELECT count(*) FROM (SELECT reading->'identifiers'->>'cik' c FROM mdm.stage_record "
                "WHERE entity_id IS NOT NULL GROUP BY 1 HAVING count(DISTINCT entity_id)>1) x")).scalar()}

def test_person_proving_run(database):
    contract, policy, keep = inputs()
    with database.admin.begin() as conn:
        register_dataset(conn, CODE, database.registry, contract)
        digest = register_policy(conn, policy)
    stage = MergeStage(Store(database.application))
    assertions = assertions_for(contract, policy, keep)
    report = {"assertions": len(assertions)}
    for n in (1, 2):
        stage.apply(batch_id=f"person-trial-{n}", run_id=str(uuid4()), policy_digest=digest,
                    consumer="person-proving", expected_checkpoint=n - 1, checkpoint=n, as_of=AS_OF,
                    assertions=assertions)
        with database.application.connect() as conn:
            report[f"after_pass_{n}"] = counts(conn)
    (W / "proving-run.json").write_text(json.dumps(report, indent=1))
    print(json.dumps(report, indent=1))
    assert report["after_pass_1"]["identities"] == report["after_pass_2"]["identities"]
