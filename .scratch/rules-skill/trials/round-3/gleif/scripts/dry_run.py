"""Step 7 dry run through the real reader.

For each member: write the picked records as a small archive in the source's own format
(one-member ZIP, JSON `{"<wrapper>":[...]}`), then run `gleif_source.inspect_archive`
(the reader's hash/format/count checks) with an on_record callback that calls
`gleif_source.record_evidence` under the contract loaded by `gleif_source.dataset_contract`
(which reads rules/sources/gleif/source.yaml). TEST inputs, labelled as such:
- metadata (content_date/file_content/record_count) comes from the file name and the sample,
  not from a verified publication manifest;
- the approved Company scope is a TEST scope made from the sample LEIs.
No database, no merge: this matches nothing against existing records.
"""

import hashlib
import io
import json
import sys
import zipfile
from collections import Counter

sys.path.insert(0, ".")
from edgar_warehouse.mdm.clean import gleif_source as gs  # noqa: E402
from edgar_warehouse.mdm.clean.adapters import FORMATS  # noqa: E402
from edgar_warehouse.mdm.clean.evidence import KINDS, validate_assertion, validate_deferred  # noqa: E402
from edgar_warehouse.mdm.clean.merge import check_company_sources  # noqa: E402
from edgar_warehouse.mdm.clean.relationships import CONTRACTS  # noqa: E402
from edgar_warehouse.mdm.clean.store import Conflict, canonical  # noqa: E402
from edgar_warehouse.rules import files  # noqa: E402

SB = sys.argv[1]
S = f"{SB}/scratch/samples"
CODES = {"level1": "gleif.level1.v1", "relationships": "gleif.relationships.v1",
         "reporting_exceptions": "gleif.reporting_exceptions.v1"}

picked = {m: [json.loads(l) for l in open(f"{S}/{m}.jsonl")] for m in CODES}


def g(row, path):
    for p in path.split("."):
        if not isinstance(row, dict):
            return None
        row = row.get(p)
    return row


# TEST scope: sample LEIs, minus a few left out on purpose to show "outside scope".
scope = set()
left_out = set()
for i, p in enumerate(picked["level1"]):
    lei = g(p["record"], "LEI.$")
    if p["target"] == "bad_lei":
        continue
    if p["target"] == "general_plain" and lei not in left_out and not left_out:
        left_out.add(lei)
        continue
    scope.add(lei)
ultimate_seen = 0
for p in picked["relationships"]:
    rel = p["record"]["RelationshipRecord"]["Relationship"]
    s, e = g(rel, "StartNode.NodeID.$"), g(rel, "EndNode.NodeID.$")
    if p["target"] == "ultimate":
        ultimate_seen += 1
        if ultimate_seen == 2:
            left_out.add(s)
            continue
    for lei in (s, e):
        if lei != "4469000001BG7ASKSB18":
            scope.add(lei)
plain = 0
for p in picked["reporting_exceptions"]:
    lei = g(p["record"], "LEI.$")
    if p["target"].startswith("plain_DIRECT"):
        plain += 1
        if plain == 2:
            left_out.add(lei)
            continue
    if lei != "4469000001BG7ASKSB18":
        scope.add(lei)
scope -= left_out

report = {"test_scope_size": len(scope), "left_out_of_scope": sorted(left_out), "members": {}}

# Contract checks the database registration and native consumption would make.
checks = {}
for member, code in CODES.items():
    c = gs.dataset_contract(member)
    a = c["adapter"]
    checks[code] = {
        "native_member_matches": a.get("native_member") == member,
        "adapter_version_is_reader": a.get("version") == gs.VERSION,
        "schema_version_is_reader": c.get("schema_version") == gs.VERSION,
        "family": c.get("family"),
        "no_classification": not a.get("classification"),
        "probable_kinds_are_kinds": all(v in KINDS for v in a.get("probable_kind_values", {}).values()),
        "formats_known": all(f is None or f in FORMATS for f in [a.get("record_key_format"), *a.get("identifier_formats", {}).values()]),
        "mapped_relationship_types_have_contracts": all(
            t in CONTRACTS for r in a.get("relationships", []) for t in r.get("type_values", {}).values()),
        "nonblocking": c.get("nonblocking_deferred_reasons"),
    }
report["contract_checks"] = checks

# The release check, with a TEST manifest (no verified ledger publication exists here).
manifest = {"publication_family": "golden_copy", "mode": "full",
            "publication_time": "2026-09-11T16:00:00+00:00",
            "sequence": gs.release_sequence("2026-09-11T16:00:00+00:00"), "members": []}
native = {"version": gs.VERSION, "record_sources": CODES, "company_leis": sorted(scope)}

all_assertions = []
for member, code in CODES.items():
    contract = gs.dataset_contract(member)
    wrapper = gs.FORMATS[member][1]
    body = ('{"%s":[\n' % wrapper + ",\n".join(json.dumps(p["record"], ensure_ascii=False) for p in picked[member]) + "\n]}").encode()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"sample-{member}.json", body)
    raw = buf.getvalue()
    path = f"{S}/sample-{member}.json.zip"
    open(path, "wb").write(raw)
    sha = hashlib.sha256(raw).hexdigest()
    metadata = {"cdf_version": gs.FORMATS[member][0], "format": "json.zip",
                "record_count": len(picked[member]),
                "content_date": "2026-09-11T16:00:00+00:00",
                "file_content": "GLEIF_FULL_PUBLISHED"}
    manifest["members"].append({"member": member, "native": metadata})
    rows = []

    def on_record(row, ordinal, member=member, code=code, contract=contract, sha=sha, rows=rows):
        kind, out = gs.record_evidence(
            row, member=member, contract=contract, source_code=code, eligible_leis=scope,
            publication={"publication_key": "dry-run", "revision": 0,
                         "artifact_sha256": sha, "member": member},
            ordinal=ordinal)
        if kind == "assertion":
            validate_assertion(out)
        else:
            validate_deferred(out)
        rows.append((picked[member][ordinal]["target"], kind, out))

    inspected = gs.inspect_archive(io.BytesIO(raw), member=member, metadata=metadata,
                                   expected_sha256=sha, on_record=on_record)
    results = []
    for target, kind, out in rows:
        if kind == "assertion":
            all_assertions.append(out)
            prov = dict(out["provenance"])
            if "source" in prov:
                prov["source"] = {k: ("<native record, %d bytes>" % len(canonical(v)) if k == "native_record" else v)
                                  for k, v in prov["source"].items()}
            results.append({"target": target, "outcome": "assertion", "kind": out["kind"],
                            "record_key": out["record_key"], "effective_at": out["effective_at"],
                            "identifiers": out["identifiers"],
                            "fields": {k: v.get("value", v["op"]) for k, v in out["fields"].items()},
                            "relationships": out["relationships"], "provenance": prov})
        else:
            results.append({"target": target, "outcome": "deferred", "reason": out["reason"],
                            "blocking": out["reason"] not in contract["nonblocking_deferred_reasons"],
                            "probable_kind": out.get("probable_kind"),
                            "record_locator": out["record_locator"]})
    report["members"][code] = {"sample_file": path, "sha256": sha,
                                "inspect_archive": {k: inspected[k] for k in ("record_count", "compressed_bytes", "expanded_bytes")},
                                "summary": Counter(f"{r['outcome']}:{r.get('reason', r.get('kind'))}:{'BLOCKING' if r.get('blocking') else 'ok'}" for r in results),
                                "records": results}

try:
    gs.validate_release(manifest, native)
    report["validate_release_test_manifest"] = "passed"
except Conflict as exc:
    report["validate_release_test_manifest"] = f"refused: {exc}"

# What the Merge Stage would say about sources before anything else (merge-rule gap).
try:
    check_company_sources(files.policy(), all_assertions)
    report["check_company_sources"] = "passed"
except Conflict as exc:
    report["check_company_sources"] = f"refused: {exc}"

json.dump(report, open(f"{SB}/scratch/dry-run.json", "w"), indent=1, default=str, ensure_ascii=False)
print(json.dumps({k: v for k, v in report.items() if k != "members"}, indent=1, default=str))
for code, m in report["members"].items():
    print("\n==", code, m["inspect_archive"], dict(m["summary"]))
    for r in m["records"]:
        print(json.dumps(r, ensure_ascii=False, default=str)[:900])
