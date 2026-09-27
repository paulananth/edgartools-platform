"""Dry run of rules/sources/gleif/source.yaml through the GLEIF reader.

Bounded sample only (scratch/sample/*.pick.json). No database. Steps:
1. zip each member's sample in Golden Copy JSON shape;
2. the reader's own archive check and JSON parser (`inspect_archive`) streams it;
3. each record goes through the reader (`record_evidence`), which reshapes it,
   applies its checks and calls `normalize` with this rules file's contract;
4. cross-checks against code that reads the result (merge, matching, relationships).

DRY_RUN_SCOPE below is a test fixture, not a proposal for the approved Company
LEI list: every LEI in it is taken from the sample records.
"""

import hashlib
import json
import sys
import tempfile
import zipfile
from pathlib import Path

S = Path(sys.argv[1])
SAMPLE = S / "scratch" / "sample"
tempfile.tempdir = str(S / "scratch" / "tmp")  # inspect_archive's snapshot stays in the sandbox
Path(tempfile.tempdir).mkdir(exist_ok=True)

from edgar_warehouse.rules import files  # noqa: E402
from edgar_warehouse.mdm.clean import gleif_source, matching, merge, store  # noqa: E402
from edgar_warehouse.mdm.clean.evidence import subject_key, validate_assertion, validate_deferred  # noqa: E402
from edgar_warehouse.mdm.clean.store import Conflict, canonical  # noqa: E402

CODES = {
    "level1": "gleif.level1.v1",
    "relationships": "gleif.relationships.v1",
    "reporting_exceptions": "gleif.reporting_exceptions.v1",
}
FILE = {
    "level1": "20260911-1600-gleif-goldencopy-lei2-golden-copy.json",
    "relationships": "20260911-1600-gleif-goldencopy-rr-golden-copy.json",
    "reporting_exceptions": "20260911-1600-gleif-goldencopy-repex-golden-copy.json",
}
LEFT_OUT = {"00TV1D5YIV5IDUGWBW29", "00EHHQ2ZHDCFXJCPCL46"}  # shown outside scope on purpose


def v(node, path):
    for part in path.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node


picks = {m: json.load(open(SAMPLE / f"{m}.pick.json")) for m in CODES}

# The dry-run scope: every LEI named in the sample except LEFT_OUT and the RR
# record picked to fall outside it.
scope = set()
for p in picks["level1"]:
    scope.add(v(p["record"], "LEI.$"))
for p in picks["relationships"]:
    if p["why"] != "start_outside_dry_run_scope":
        rel = v(p["record"], "RelationshipRecord.Relationship")
        scope |= {v(rel, "StartNode.NodeID.$"), v(rel, "EndNode.NodeID.$")}
for p in picks["reporting_exceptions"]:
    scope.add(v(p["record"], "LEI.$"))
scope -= LEFT_OUT
MODE = sys.argv[2] if len(sys.argv) > 2 else "all-sample-leis"
if MODE == "general-only":
    # Only LEIs whose Level 1 record in the sample is GENERAL; RR edge-case and
    # REPEX LEIs (no Level 1 record in the sample) stay, to exercise their paths.
    scope -= {v(p["record"], "LEI.$") for p in picks["level1"]
              if v(p["record"], "Entity.EntityCategory.$") != "GENERAL"}

source = files.source("gleif")
report = {"scope_size": len(scope), "members": {}, "checks": {}}


class _NoDatabase:
    """Stands in for a connection: register_dataset's own checks run first."""

    def execute(self, *a, **k):
        raise RuntimeError("reached the database step: contract checks passed")


for member, code in CODES.items():
    contract = source["mdm"][code]["contract"]
    # register_dataset validates reasons, probable kinds and formats before it
    # queries the registry. A stub connection stops it there.
    try:
        store.register_dataset(_NoDatabase(), code, "00000000-0000-0000-0000-000000000000", contract)
        registered = "no database step reached (unexpected)"
    except RuntimeError as exc:
        registered = str(exc)
    except (ValueError, Conflict) as exc:
        registered = f"REFUSED: {exc}"
    # The consumer's own contract check (native_consumption.prepare_native).
    consumer_ok = (
        contract["adapter"].get("native_member") == member
        and contract["adapter"].get("version") == gleif_source.VERSION
        and contract.get("schema_version") == gleif_source.VERSION
        and contract.get("family") == "gleif"
    )

    rows = [p["record"] for p in picks[member]]
    wrapper = gleif_source.FORMATS[member][1]
    raw = json.dumps({wrapper: rows}, ensure_ascii=False, indent=4).encode()
    zpath = SAMPLE / f"{member}.dry-run.json.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(FILE[member], raw)
    sha = hashlib.sha256(zpath.read_bytes()).hexdigest()
    metadata = {
        "cdf_version": gleif_source.FORMATS[member][0],
        "format": "json.zip",
        "record_count": len(rows),
        "content_date": "2026-09-11T16:00:00+00:00",
        "file_content": "GLEIF_FULL_PUBLISHED",
        "delta_start": None,
    }
    publication = {"artifact_sha256": sha, "member": FILE[member], "publication_key": "dry-run", "revision": 0}
    results = []

    def on_record(row, ordinal):
        kind, body = gleif_source.record_evidence(
            row, member=member, contract=contract, source_code=code,
            eligible_leis=scope, publication=publication, ordinal=ordinal,
        )
        # the same record read twice gives the same id
        again = gleif_source.record_evidence(
            row, member=member, contract=contract, source_code=code,
            eligible_leis=scope, publication=publication, ordinal=ordinal,
        )[1]
        (validate_assertion if kind == "assertion" else validate_deferred)(body)
        results.append((ordinal, kind, body, body == again))

    with zpath.open("rb") as stream:
        inspected = gleif_source.inspect_archive(
            stream, member=member, metadata=metadata, expected_sha256=sha, on_record=on_record
        )

    shown = []
    for (ordinal, kind, body, stable), pick in zip(results, picks[member]):
        item = {"ordinal_in_sample": ordinal, "picked_because": pick["why"],
                "ordinal_in_file": pick["ordinal"], "outcome": kind, "stable_id": stable}
        if kind == "assertion":
            item.update(
                record_key=body["record_key"], kind=body["kind"], subject=body["subject"],
                effective_at=body["effective_at"], identifiers=body["identifiers"],
                fields={k: (f.get("value") if f["op"] == "value" else f"<{f['op']}>")
                        for k, f in body["fields"].items()},
                relationships=body["relationships"],
                matching=body["provenance"].get("matching"),
                provenance_keys=sorted(body["provenance"]),
                native_record_kept=bool(body["provenance"].get("source", {}).get("native_record")),
                assertion_id=body["assertion_id"],
                assertion_bytes=len(canonical(body)),
            )
        else:
            reason = body["reason"]
            item.update(
                reason=reason,
                blocks=reason not in contract.get("nonblocking_deferred_reasons", []),
                probable_kind=body.get("probable_kind"),
                record_locator=body["record_locator"],
                lei=v(body["raw_record"], "LEI.$")
                or v(body["raw_record"], "RelationshipRecord.Relationship.StartNode.NodeID.$"),
            )
        shown.append(item)
    report["members"][member] = {
        "source_code": code,
        "register_dataset_checks": registered,
        "consumer_contract_check": consumer_ok,
        "archive": {k: inspected[k] for k in ("record_count", "compressed_bytes", "expanded_bytes")},
        "sample_zip_sha256": sha,
        "records": shown,
    }

# Cross-checks on what the rest of Clean MDM reads.
l1 = {r["identifiers"]["lei"]: r for r in report["members"]["level1"]["records"] if r["outcome"] == "assertion"}
rr = [r for r in report["members"]["relationships"]["records"] if r["outcome"] == "assertion"]
targets = []
for r in rr:
    for rel in r["relationships"]:
        end = next(p for p in picks["relationships"] if p["ordinal"] == r["ordinal_in_file"])
        end_lei = v(end["record"], "RelationshipRecord.Relationship.EndNode.NodeID.$")
        targets.append({
            "type": rel["type"],
            "end_lei": end_lei,
            "target_subject_is_level1_subject_of_end": rel["target_subject"] == subject_key("gleif.level1.v1", end_lei),
            "end_level1_record_in_sample_as_company": end_lei in l1,
        })
report["checks"]["relationship_targets"] = targets

policy = files.policy()
full = {}
for member, code in CODES.items():
    contract = source["mdm"][code]["contract"]
    full[member] = []
    for p in picks[member]:
        kind, body = gleif_source.record_evidence(
            p["record"], member=member, contract=contract, source_code=code,
            eligible_leis=scope, publication={"artifact_sha256": "0" * 64, "member": FILE[member],
                                              "publication_key": "dry-run", "revision": 0},
            ordinal=0)
        if kind == "assertion":
            full[member].append(body)
for member in CODES:
    try:
        merge.check_company_sources(policy, full[member])
        report["checks"][f"check_company_sources:{member}"] = f"passes ({len(full[member])} assertions)"
    except Conflict as exc:
        report["checks"][f"check_company_sources:{member}"] = f"FAILS: {exc}"

rule = next(r for r in policy["kinds"]["company"]["rules"] if r["rule_id"] == "sec-gleif-name-postal")
eligible_args = next(t["args"] for t in rule["when"] if t["primitive"] == "gleif_entity_eligible@1")
report["checks"]["matching_reads"] = [
    {
        "lei": a["identifiers"]["lei"],
        "gleif_entity_eligible": matching._eligible(None, a, eligible_args),
        "jurisdiction": matching._read(a, "jurisdiction"),
        "headquarters_postal_code": matching._read(a, "matching.headquarters_postal_code"),
        "headquarters_country": matching._read(a, "matching.headquarters_country"),
        "name_for_census": matching._value(a, "name"),
        "last_update_for_census": matching._value(a, "gleif_last_update"),
        "raw_last_update": v(next(p["record"] for p in picks["level1"] if v(p["record"], "LEI.$") == a["identifiers"]["lei"]),
                             "Registration.LastUpdateDate.$"),
    }
    for a in full["level1"]
]

report["scope_mode"] = MODE
out = S / "scratch" / ("dry-run.json" if MODE == "all-sample-leis" else f"dry-run-{MODE}.json")
json.dump(report, open(out, "w"), indent=1, ensure_ascii=False, default=str)
print(f"wrote {out}")
