"""Ticket 32, third run: the sandbox's rules mastered once more, by this script and not the agent's, on fresh
stores: the agent's inputs read-only, every output outside the sandbox. All four parts merged a second time under
new batch ids and consumers (the agent left Company out). Counts and digests only."""
import hashlib, json, os, shlex, sys, time
from collections import Counter
from pathlib import Path
from uuid import uuid4
from sqlalchemy import create_engine
from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.change_journal.store import ChangeJournal
from edgar_warehouse.mdm.clean import inspection
from edgar_warehouse.mdm.clean.record_reads import RecordReader, for_connection
from edgar_warehouse.mdm.clean.store import register_dataset, register_policy
from edgar_warehouse.mdm.clean.target_manifest import write_manifest
from edgar_warehouse.rules import files, proving
from edgar_warehouse.rules.db import Rules
from edgar_warehouse.rules.driving import Commands, duties

S, stores, OUT = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
PREPARE_ARGS = shlex.split(sys.argv[4])
W = S / "work"
assert str(files.ROOT).startswith(str(S)), files.ROOT
start = time.monotonic()
env = duties(stores)
mdm = create_engine(env["governance"]["RULES_MDM_ACTIVATION_DATABASE_URL"])
rules = Rules(create_engine(env["governance"]["RULES_DATABASE_URL"]))
journal = ChangeJournal(create_engine(env["worker"]["CHANGE_JOURNAL_DATABASE_URL"]))
policy = files.policy(); root = OUT / "work" / uuid4().hex[:6]; root.mkdir(parents=True)
store = Artifacts()
commands = Commands(env, (root / "reports").as_uri(), deadline=time.monotonic() + 2400, log=root / "errors.log")
AS_OF = "2026-10-31T10:00:00+00:00"
def digest(value): return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
def say(**k): print(json.dumps({"minutes": round((time.monotonic() - start) / 60, 1), **k}, default=str), flush=True)

with mdm.begin() as conn:
    register_policy(conn, policy)
    for source, cap in (("sec.submissions.company", "capture-sec"), ("gleif", "capture-gleif"), ("sec.submissions.person", "capture-sec")):
        sha = hashlib.sha256((W / cap / "receipts.jsonl").read_bytes()).hexdigest()
        for code, entry in files.source(source)["mdm"].items():
            register_dataset(conn, code, entry["contract"], rules_authority=proving.sandbox_authority(source, code, entry["contract"], sha))

seen = set()
def run(source, target, manifest, steps=None):
    doc = files.source(source); name = f"proof3.{source}.{target}"
    steps = steps or doc["bookkeeping"]["targets"][target]["steps"]
    if name not in seen:
        seen.add(name)
        book = {**doc["bookkeeping"], "targets": {**doc["bookkeeping"]["targets"], target: {**doc["bookkeeping"]["targets"]["mastering"], "steps": steps}}}
        saved = rules.save("source", name, "1", {"source": name, "bookkeeping": book})
        rules.prove("source", name, "1", {"digest": saved["digest"], "passed": True, "batch_hash": manifest["sha256"]})
        rules.activate("source", name, "1")
    out = commands("worker", "rules", "run", "--source", name, "--target", target, "--input-manifest", manifest["uri"], "--input-sha256", manifest["sha256"])
    final = commands.drive(str(json.loads(out)["run"]["run_id"]), steps)
    say(stage=f"{source} {target}", state=final["run"]["state"])
    assert final["run"]["state"] == "complete", final["run"]["state"]

def snapshot():
    found = inspection.counts(mdm)
    masters, stage, bound, groups, relations = Counter(), Counter(), Counter(), {}, 0
    with mdm.connect().execution_options(isolation_level="REPEATABLE READ") as conn:
        reader = for_connection(conn)
        for page in inspection._pages(reader.adapter, conn, "source-record", lookup=True):
            pointers = reader.current([key for key, _ in page]); reader._readings(pointers)
            for subject, body in pointers.items():
                stage[f"{body['source_code']}:{body['kind']}"] += 1
                if body.get("entity_id"):
                    bound[body["source_code"]] += 1; groups.setdefault(body["entity_id"], []).append(subject)
        for page in inspection._pages(reader.adapter, conn, "entity"):
            for _, row in page:
                body = RecordReader._body(row)
                if body.get("status") != "alias": masters[body.get("kind") or "(none)"] += 1
        for page in inspection._pages(reader.adapter, conn, "relationship"): relations += len(page)
        types = reader.adapter.count_types(("entity", "relationship", "review"), connection=conn)
    return ({"masters": dict(sorted(masters.items())), "stage_records": dict(sorted(stage.items())), "stage_bound": dict(sorted(bound.items())),
             "open_reviews": found["open_reviews"], "set_aside": found["set_aside"], "decisions": found["decisions"],
             "identifiers_on_two_masters": found["identifiers_on_two_masters"], "relationships": relations, "count_types": types},
            {"bindings": digest(sorted(sorted(g) for g in groups.values())), "current_records_md5": found["current_records_md5"]},
            dict(found["changes"]))

# First pass, in the agent's order.
out = commands("worker", "mdm", "prepare-clean-company", *PREPARE_ARGS, "--output", str(root / "company"))
company = json.loads(out.strip().splitlines()[-1])["manifest"]
run("sec.submissions.company", "mastering", company)
batches = {"company": root / "company"}
for source, target, cap, docs in (("gleif", "mastering", "capture-gleif", "gleif-level1"), ("gleif", "relationships", "capture-gleif", "gleif-relationships"), ("sec.submissions.person", "mastering", "capture-sec", "sec-documents")):
    folder = root / f"{source}-{target}"
    r = write_manifest(source=source, target=target, capture=str(W / cap), documents=str(W / f"manifests/{docs}.json"), capture_run="proof3-capture",
                       output=str(folder), as_of=AS_OF, revision=0, force=True, journal=journal)
    run(source, target, r["manifest"])
    batches[f"{source}-{target}"] = folder
first = snapshot(); say(stage="first pass", counts=first[0], digests=first[1], writes=first[2])
(OUT / "report.json").write_text(json.dumps({"first": first}, indent=1, sort_keys=True, default=str))

# Second pass: each verified record set merged again under new batch ids and consumers.
MERGE = {"name": "merge", "operation": "mdm.merge", "requires": [], "key": "{batch_id}", "leases": ["mdm:consumer:{consumer}"], "checks": ["mdm.committed"]}
for tag, folder in batches.items():
    found = [p for p in folder.rglob("manifest.json") if "batches" in json.loads(p.read_text())]
    assert len(found) == 1, (tag, found)
    body = json.loads(found[0].read_text())
    for batch in body["batches"]:
        batch["batch_id"], batch["consumer"] = f"{batch['batch_id']}:second", f"{batch['consumer']}:second"
    ref = store.put_bytes((found[0].parent / "manifest-second.json").as_uri(), json.dumps(body).encode())
    manifest = store.put(root.as_uri(), {"version": 2, "steps": {"merge": [{"keys": {"batch_id": f"{tag}-second-merge", "consumer": f"{tag}-second"}, "input": ref,
                         "output": (root / f"{tag}-second-merged.json").as_uri(), "cursor": {}}]}})
    source = "gleif" if tag.startswith("gleif") else "sec.submissions.person" if "person" in tag else "sec.submissions.company"
    run(source, f"replay-{tag}", manifest, [MERGE])
second = snapshot(); say(stage="second pass", counts=second[0], digests=second[1], writes=second[2])
report = {"first": first, "second": second, "second_pass_changed_nothing": first[:2] == second[:2] and first[2] == second[2], "minutes": round((time.monotonic() - start) / 60, 1)}
(OUT / "report.json").write_text(json.dumps(report, indent=1, sort_keys=True, default=str))
say(stage="end", second_pass_changed_nothing=report["second_pass_changed_nothing"])
