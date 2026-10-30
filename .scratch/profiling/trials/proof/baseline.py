"""Recreation proof (ticket 32), steps 4 and 6: one rules folder mastered on the 500-entity cohort.

The same script masters today's rules (the baseline) and the cold agent's regenerated rules
(the sandbox): `EDGAR_RULES_ROOT` names the rules folder for this process and for the
installed workers, and the report names the folder and every rules file's sha256.

One set of empty stores, loaded only by the installed bundle's workers, each step checked by
a verifier under its own login (as ticket 135's proof, `.scratch/mastering-to-done/proof/
installed_mastering_proof.py`). The harness only provisions: it registers the policy and the
four Dataset Contracts and approves its own proof pipeline.

Inputs, on this machine only (no provider request; operator, 2026-10-07: "Local feeds only"):
- SEC: the cohort's 500 main submissions documents (`p08/inputs/sec/receipts.jsonl`), read from
  the capture they were sliced from (`all-76230`; every receipt's sha256 is equal). Company
  preparation takes the 445 the recorded Name Census counted (`cm27-raw`); the Person target,
  which reads and classifies every filer, takes all 500 (ticket 32, decided from the data);
- GLEIF: the captured Golden Copy of 2026-09-11 16:00, Level 1 and relationships, each read by its
  configured Rust reading with the slice's 2,545 LEIs as `approved_scope`.

Passes: SEC Company, SEC Person, GLEIF Level 1, GLEIF relationships; then the second pass: each
target's verified records merged again under new batch ids and consumers, which must change
nothing. The report holds counts and digests only.

    COMPANY_PROOF_OUT=<report.json> [EDGAR_RULES_ROOT=<rules>] PATH="$HOME/.cargo/bin:$PATH" \\
      uv run --no-sync pytest -q -s -p no:randomly .scratch/profiling/trials/proof/baseline.py
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections import Counter
from pathlib import Path

from sqlalchemy import create_engine

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.bookkeeping.clean.database import grant_profile
from edgar_warehouse.bookkeeping.clean.destinations import migrate_guard
from edgar_warehouse.mdm.clean import inspection
from edgar_warehouse.mdm.clean.record_reads import RecordReader, for_connection
from edgar_warehouse.mdm.clean.store import canonical, digest, migrate, register_policy
from edgar_warehouse.rules import files
from tests.engine.test_data_skill_bundle_postgres import _run, _stores, installed  # noqa: F401
from tests.integration.test_configured_bookkeeping_postgres import databases  # noqa: F401
from tests.support.rules_approval import approve
from tests.support.rules_authority import register_dataset

PROVING = Path("~/.local/share/edgartools/clean-mdm/proving").expanduser()
SLICE = PROVING / "p08" / "inputs"
CENSUS = PROVING / "cm27-raw"
CAPTURE = Path("~/.local/share/edgartools/clean-mdm/captures/sec.submissions.company/all-76230").expanduser()
GOLDEN = Path("~/.local/share/edgartools/clean-mdm/captures/gleif/20260911-1600").expanduser()
LEVEL1 = (GOLDEN / "01-20260911-1600-gleif-goldencopy-lei2-golden-copy.json.zip", 3428477)
RELATIONSHIPS = (GOLDEN / "01-20260911-1600-gleif-goldencopy-rr-golden-copy.json.zip", 487721)
CATALOG = "warehouse/bronze/reference/sec/company_tickers_exchange/2026/09/02/company_tickers_exchange.json"
OBSERVED_AT, CATALOG_RUN = "2026-09-30T02:20:28+00:00", "local-cm27-tickers-20260902"
AS_OF = "2026-09-29T15:00:00+00:00"
COMPANY, PERSON = "sec.submissions.company.v1", "sec.submissions.person.v1"
LEVEL1_CODE, RELATIONSHIP_CODE = "gleif.level1.v1", "gleif.relationships.v1"
LIMIT = "1000"
TARGET = lambda steps: {"lease_seconds": 300, "heartbeat_seconds": 20,  # noqa: E731
                        "retry": {"attempts": 5, "base_ms": 100, "cap_ms": 5000}, "allow_zero_work": False,
                        "steps": steps, "checks": ["manifest.hash", "work.accounting", "journal.delivered"]}
MERGE = {"name": "merge", "operation": "mdm.merge", "requires": [], "key": "{batch_id}",
         "leases": ["mdm:consumer:{consumer}"], "checks": ["input.hash", "output.receipt", "mdm.committed"]}
PREPARE = {"name": "prepare", "operation": "mdm.prepare", "requires": [], "key": "{batch_id}",
           "leases": ["mdm-prepare:{batch_id}"], "checks": ["input.hash", "output.receipt", "mdm.prepared"]}
READ = {"name": "read", "operation": "source.read", "requires": [], "key": "{batch_id}",
        "leases": ["source-output:{batch_id}"], "checks": ["input.hash", "output.receipt", "source.output"]}


def _steps(source: str) -> list[dict]:
    return files.source(source)["bookkeeping"]["targets"]["mastering"]["steps"]


PIPELINE = {"pipeline": "recreation-baseline", "bookkeeping": {"version": 1, "targets": {
    "company": TARGET(_steps("sec.submissions.company")),
    "person": TARGET(_steps("sec.submissions.person")),
    "gleif": TARGET([READ, {**PREPARE, "requires": ["read"]}, {**MERGE, "requires": ["prepare"]}]),
    "replay": TARGET([MERGE]),
    "gleif-replay": TARGET([PREPARE, {**MERGE, "requires": ["prepare"]}])}}}
PROFILES = ("source.read", "source.combine", "mdm.prepare", "mdm.merge", "journal.record")


def cohort() -> tuple[list[str], list[str]]:
    """The cohort's main submissions documents: those the Name Census counted, and all."""
    keys = sorted(json.loads(line)["key"] for line in (SLICE / "sec" / "receipts.jsonl").open())
    main = [k for k in keys if "/main/" in k]
    counted = set(json.loads((CENSUS / "population.json").read_text()))
    return [k for k in main if k in counted], main


def scope() -> list[str]:
    """The slice's GLEIF Level 1 LEIs: the approved scope of both GLEIF readings."""
    return sorted({json.loads(line)["record"]["LEI"]["$"] for line in (SLICE / "gleif" / "level1.jsonl").open()})


def rules_files() -> dict[str, str]:
    """Every rules file's sha256 under the rules folder this run reads."""
    return {str(p.relative_to(files.ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(files.ROOT.rglob("*")) if p.is_file()}


def code_sets() -> dict[str, str]:
    """Each published RDM code set version's pinned sha256 (the RDM part of DIFF.md)."""
    return {f"{pin.parent.parent.name}/{pin.parent.name}": json.loads(pin.read_text())["sha256"]
            for pin in sorted((files.ROOT / "reference" / "published").glob("*/*/pin.json"))}


def test_recreation_baseline(installed, databases, tmp_path):  # noqa: F811
    python, root = installed
    store = Artifacts()
    out = Path(os.environ["COMPANY_PROOF_OUT"])
    started = time.monotonic()
    timings: dict[str, float] = {}
    minutes = lambda: round((time.monotonic() - started) / 60, 1)  # noqa: E731
    say = lambda **fields: print(json.dumps({"at": time.strftime("%H:%M:%S"), **fields}), flush=True)  # noqa: E731
    counted, everyone = cohort()
    leis = scope()

    for profile in PROFILES:
        grant_profile(databases.admin, profile=profile, worker="bk_runtime", verifier="bk_verifier")
    with databases.admin.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.exec_driver_sql("CREATE DATABASE mdm_proof")
    mdm_admin = create_engine(databases.admin.url.set(database="mdm_proof"))
    mdm_app = create_engine(mdm_admin.url.set(username="clean_application", password="test"))
    migrate(mdm_admin, application_role="clean_application")
    migrate_guard(mdm_admin, runtime_role="clean_application")
    with mdm_admin.begin() as conn:
        policy = register_policy(conn, files.policy())
        register_dataset(conn, COMPANY, "1", files.mdm_contract("sec.submissions.company", COMPANY))
        register_dataset(conn, PERSON, "1", files.mdm_contract("sec.submissions.person", PERSON))
        register_dataset(conn, LEVEL1_CODE, "1", files.mdm_contract("gleif", LEVEL1_CODE))
        register_dataset(conn, RELATIONSHIP_CODE, "1", files.mdm_contract("gleif", RELATIONSHIP_CODE))
        for schema in ("mdm", "public"):  # governed storage keeps its tables in `public`
            conn.exec_driver_sql(f"GRANT USAGE ON SCHEMA {schema} TO bk_verifier")
            conn.exec_driver_sql(f"GRANT SELECT ON ALL TABLES IN SCHEMA {schema} TO bk_verifier")
    mdm_reader = create_engine(mdm_admin.url.set(username="bk_verifier", password="test"))
    say(stage="provisioned", rules=str(files.ROOT), policy=policy, company_documents=len(counted),
        person_documents=len(everyone), gleif_scope=len(leis))

    url = lambda engine: engine.url.render_as_string(hide_password=False)  # noqa: E731
    env = {**_stores(databases), "BOOKKEEPING_MANIFEST_ROOT": (tmp_path / "control").as_uri(),
           "EDGAR_RULES_ROOT": str(files.ROOT)}
    worker = {**env, "MDM_DATABASE_URL": url(mdm_app), "MDM_APPLICATION_ROLE": "clean_application"}
    verifier = {**env, "BOOKKEEPING_DATABASE_URL": url(databases.verifier), "MDM_DATABASE_URL": url(mdm_reader)}

    def cli(*args, env=env):
        done = _run(python, "-m", "edgar_warehouse.cli", *args, env=env, cwd=root)
        assert done.returncode == 0, done.stderr[-4000:]
        return done.stdout

    def documents(name: str, keys: list[str]) -> Path:
        path = tmp_path / f"{name}-documents.json"
        path.write_text(json.dumps(keys))
        return path

    # The two SEC manifests, by the installed CLI.
    company = json.loads(cli(
        "mdm", "prepare-clean-company", "--capture", str(CAPTURE), "--documents", str(documents("company", counted)),
        "--population", str(CENSUS / "population.json"), "--name-census", str(CENSUS / "census.json"),
        "--catalog", CATALOG, "--capture-run", "p08-company", "--catalog-run", CATALOG_RUN,
        "--observed-at", OBSERVED_AT, "--output", str(tmp_path / "company"), "--as-of", AS_OF, "--revision", "0"))
    person = json.loads(cli(
        "mdm", "prepare-capture", "--source", "sec.submissions.person", "--capture", str(CAPTURE),
        "--documents", str(documents("person", everyone)), "--capture-run", "p08-person",
        "--output", str(tmp_path / "person"), "--as-of", AS_OF, "--revision", "0"))
    assert company["policy_digest"] == policy and company["manifest"] and person["manifest"], (company, person)

    def gleif_units(name: str, contract: str, table: str, dataset: str, archive: tuple[Path, int]) -> dict:
        """One GLEIF member through its configured reading, the slice's LEIs as its approved scope."""
        body = files.load(files.ROOT / "sources" / "gleif" / contract)
        body["read"]["references"]["approved_scope"] = {lei: {"selected": True} for lei in leis}
        path, count = archive
        raw = store.put_bytes(path.as_uri(), path.read_bytes())
        context = store.put(tmp_path.as_uri(), {"version": 1, "input": raw, "values": {"publication_count": count}})
        artifact = {"input": raw, "context": context}
        if "lookup_sets" in body["read"]:  # Level 1's N-PORT issuer set: empty, it flags no record
            artifact["lookups"] = store.put(tmp_path.as_uri(), {"version": 1, "input": raw,
                                                                "sets": {s: [] for s in body["read"]["lookup_sets"]}})
        reading = store.put(tmp_path.as_uri(), {"version": 3 if "lookups" in artifact else 2,
                                                "contract": store.put(tmp_path.as_uri(), body), "artifacts": [artifact]})
        keys = {"batch_id": f"{name}-first", "consumer": f"{dataset}:first"}
        base = tmp_path / name
        return store.put(tmp_path.as_uri(), {"version": 2, "steps": {
            "read": [{"keys": keys, "input": reading, "output": (base / "reading.json").as_uri(), "cursor": {}}],
            "prepare": [{"keys": {**keys, "table": table, "dataset": dataset, "record_column": "record",
                                  "policy": policy, "as_of": AS_OF},
                         "input": {"from": {"step": "read", "key": keys["batch_id"]}},
                         "output": (base / "mdm" / "manifest.json").as_uri(), "cursor": {}}],
            "merge": [{"keys": keys, "input": {"from": {"step": "prepare", "key": keys["batch_id"]}},
                       "output": (base / "merged.json").as_uri(), "cursor": {}}]}})

    level1 = gleif_units("level1", "level1-json.yaml", "level1", LEVEL1_CODE, LEVEL1)
    relationships = gleif_units("relationships", "relationships-json.yaml", "relationships", RELATIONSHIP_CODE,
                                RELATIONSHIPS)

    saved = databases.rules.save("pipeline", PIPELINE["pipeline"], "1", PIPELINE)
    databases.rules.prove("pipeline", PIPELINE["pipeline"], "1",
                          {"digest": saved["digest"], "batch_hash": company["manifest"]["sha256"], "passed": True})
    approve(databases.approver, "pipeline", PIPELINE["pipeline"], "1")
    databases.rules.activate("pipeline", PIPELINE["pipeline"], "1")

    def submit(target: str, manifest: dict) -> str:
        return json.loads(cli("rules", "run", "--pipeline", PIPELINE["pipeline"], "--target", target,
                              "--input-manifest", manifest["uri"], "--input-sha256", manifest["sha256"]))["run"]["run_id"]

    def drive(run_id: str) -> None:
        """Work and verify every profile until every item is verified, then finalize."""
        deadline = time.monotonic() + 3 * 3600
        while True:
            for profile in PROFILES:
                cli("workers", "work", profile, run_id, "--limit", LIMIT, env=worker)
                cli("workers", "verify", profile, run_id, "--reports", (tmp_path / "reports").as_uri(),
                    "--limit", LIMIT, env=verifier)
            items = json.loads(cli("bookkeeping", "status", run_id))["items"]
            if items and all(i["state"] == "verified" for i in items):
                break
            failed = [i for i in items if i["state"] in ("failed", "rejected")]
            assert not failed, failed[:3]
            assert time.monotonic() < deadline, [i for i in items if i["state"] != "verified"][:3]
            time.sleep(2)
        cli("bookkeeping", "finalize", run_id)
        assert json.loads(cli("bookkeeping", "status", run_id))["run"]["state"] == "complete"

    for name, target, manifest in (("company", "company", company["manifest"]), ("person", "person", person["manifest"]),
                                   ("level1", "gleif", level1), ("relationships", "gleif", relationships)):
        drive(submit(target, manifest))
        timings[name] = minutes()
        say(stage=f"{name} merged", minutes=minutes())

    def snapshot() -> tuple[dict, dict]:
        """Counts and digests read through the record reader: masters by kind (aliases left out),
        stage records and bindings by source, reviews, decisions, and the relationships."""
        found = inspection.counts(mdm_reader)
        masters, stage, bound, groups, relations = Counter(), Counter(), Counter(), {}, []
        with mdm_reader.connect().execution_options(isolation_level="REPEATABLE READ") as conn:
            reader = for_connection(conn)
            subjects = {}
            for page in inspection._pages(reader.adapter, conn, "source-record", lookup=True):
                pointers = reader.current([key for key, _ in page])
                reader._readings(pointers)
                for subject, body in pointers.items():
                    stage[f"{body['source_code']}:{body['kind']}"] += 1
                    if body.get("entity_id"):
                        bound[body["source_code"]] += 1
                        groups.setdefault(body["entity_id"], []).append(subject)
                        subjects.setdefault(body["entity_id"], []).append(subject)
            for page in inspection._pages(reader.adapter, conn, "entity"):
                for _, row in page:
                    body = RecordReader._body(row)
                    if body.get("status") != "alias":
                        masters[body.get("kind") or "(none)"] += 1
            # A relationship names its two masters by minted ids; each is read as its bound records'
            # subjects, so two runs that bind the same records compare equal.
            for page in inspection._pages(reader.adapter, conn, "relationship"):
                for _, row in page:
                    body = RecordReader._body(row)
                    ends = {k: sorted(subjects.get(v, [v])) for k, v in body.items() if k.endswith("_id")
                            and isinstance(v, str) and v in subjects}
                    relations.append(canonical({**{k: v for k, v in body.items() if k not in ends}, **ends}))
        counts = {"masters": dict(sorted(masters.items())), "stage_records": dict(sorted(stage.items())),
                  "stage_bound": dict(sorted(bound.items())), "open_reviews": found["open_reviews"],
                  "set_aside": found["set_aside"], "decisions": found["decisions"],
                  "identifiers_on_two_masters": found["identifiers_on_two_masters"],
                  "relationships": len(relations)}
        digests = {"bindings": digest(sorted(sorted(g) for g in groups.values())),
                   "relationships": digest(sorted(relations)), "current_records_md5": found["current_records_md5"],
                   **{f"writes_{k}": v for k, v in found["changes"].items()}}
        return counts, digests

    first, first_digests = snapshot()
    say(stage="first pass", **first, digests=first_digests)

    # The second pass: each verified record set merged again under new batch ids and consumers.
    def remerge(folder: Path, tag: str) -> dict:
        manifest = json.loads((folder / "manifest.json").read_text())
        for batch in manifest["batches"]:
            batch["batch_id"], batch["consumer"] = f"{batch['batch_id']}:{tag}", f"{batch['consumer']}:{tag}"
        ref = store.put_bytes((folder / f"manifest-{tag}.json").as_uri(), json.dumps(manifest).encode())
        return store.put(tmp_path.as_uri(), {"version": 2, "steps": {"merge": [
            {"keys": {"batch_id": f"{tag}-merge", "consumer": f"{tag}"}, "input": ref,
             "output": (tmp_path / f"{tag}-merged.json").as_uri(), "cursor": {}}]}})

    def replay(name: str, dataset: str, table: str) -> dict:
        reading = tmp_path / name / "reading.json"
        ref = {"uri": reading.as_uri(), "sha256": hashlib.sha256(reading.read_bytes()).hexdigest()}
        keys = {"batch_id": f"{name}-second", "consumer": f"{dataset}:second"}
        base = tmp_path / f"{name}-second"
        return store.put(tmp_path.as_uri(), {"version": 2, "steps": {
            "prepare": [{"keys": {**keys, "table": table, "dataset": dataset, "record_column": "record",
                                  "policy": policy, "as_of": AS_OF},
                         "input": ref, "output": (base / "mdm" / "manifest.json").as_uri(), "cursor": {}}],
            "merge": [{"keys": keys, "input": {"from": {"step": "prepare", "key": keys["batch_id"]}},
                       "output": (base / "merged.json").as_uri(), "cursor": {}}]}})

    for target, manifest in (("replay", remerge(tmp_path / "company" / "records", "company-second")),
                             ("replay", remerge(tmp_path / "person" / "records", "person-second")),
                             ("gleif-replay", replay("level1", LEVEL1_CODE, "level1")),
                             ("gleif-replay", replay("relationships", RELATIONSHIP_CODE, "relationships"))):
        drive(submit(target, manifest))
    second, second_digests = snapshot()
    timings["second_pass"] = minutes()
    say(stage="second pass", digests=second_digests)

    report = {"goal": "Recreation proof (ticket 32): one rules folder mastered on the 500-entity cohort",
              "rules_root": str(files.ROOT), "rules_files": rules_files(), "code_sets": code_sets(),
              "policy": policy, "company_documents": len(counted), "person_documents": len(everyone),
              "gleif_scope_leis": len(leis), "after_first_pass": first, "digests": first_digests,
              "second_pass_changed_nothing": (first, first_digests) == (second, second_digests),
              "second_pass_digests": second_digests, "minutes_since_start": timings, "minutes": minutes()}
    out.write_text(json.dumps(report, sort_keys=True, indent=1) + "\n")
    say(stage="report", second_pass_changed_nothing=report["second_pass_changed_nothing"], minutes=minutes())
    # No silent zeros: every source staged and bound something.
    for code in (COMPANY, PERSON, LEVEL1_CODE):
        assert first["stage_bound"].get(code, 0) > 0, (code, first["stage_bound"])
    assert first["relationships"] > 0 and not first["identifiers_on_two_masters"], first
    assert report["second_pass_changed_nothing"], (first, second, first_digests, second_digests)
