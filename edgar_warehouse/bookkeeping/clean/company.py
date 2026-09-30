"""Bounded, offline SEC Company scope preparation and pagination expansion."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from urllib.parse import quote
from urllib.parse import unquote, urlparse
from pathlib import Path
from uuid import UUID

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.bookkeeping.clean.config import Blocked, Capability, canonical, digest, generated_worklist, reference

SOURCE = "sec.submissions.company"
FEED = "submissions"
_CIK = re.compile(r"[0-9]{10}")
_PAGE = re.compile(r"CIK[0-9]{10}-submissions-[0-9]{3,6}\.json")


def _decision(*, cik: str, file: str, cause: dict, prior: dict | None = None) -> dict:
    candidate = f"submissions/{cause['sha256']}/{cik}/{file}"
    url = (f"https://data.sec.gov/submissions/CIK{cik}.json" if file == "main"
           else f"https://data.sec.gov/submissions/{quote(file)}")
    return {"version": 1, "source": SOURCE, "feed": FEED,
            "scope": {"cik": cik, "file": file},
            "request": {"candidate_id": candidate, "source_family": FEED,
                        "logical_source_key": candidate, "source_url": url,
                        "cause": "DUE_POLICY", "cause_reference": cause["uri"],
                        "disposition": "FETCH_AUTHORIZED", "blocker": None,
                        "next_action": "capture", "owner_role": "ACQUISITION_COORDINATOR"},
            "prior": prior, "evidence": [cause]}


def _unit(cik: str, file: str, decision: dict, output_root: str, artifacts: Artifacts) -> dict:
    ref = artifacts.put(output_root.rstrip("/") + "/decisions", decision)
    candidate = decision["request"]["candidate_id"]
    return {"keys": {"source": SOURCE, "feed": FEED, "cik": cik, "file": file,
                     "candidate_id": candidate},
            "input": ref,
            "output": output_root.rstrip("/") + f"/capture/{cik}/{file}.json",
            "cursor": {"candidate_id": candidate}}


def prepare_company(*, scope_ref: dict, support_ref: dict, output_root: str,
                    artifacts: Artifacts | None = None) -> dict:
    """Write only frozen input artifacts. No provider, Rules or database call."""
    artifacts = artifacts or Artifacts()
    _local_path(output_root)
    reference(scope_ref)
    reference(support_ref)
    scope = artifacts.json(scope_ref)
    support = artifacts.json(support_ref)
    if (set(scope) not in ({"version", "ciks", "prior"}, {"version", "ciks", "prior", "revisions"})
            or scope["version"] != 1
            or not isinstance(scope["ciks"], list) or not 1 <= len(scope["ciks"]) <= 1000
            or any(not isinstance(cik, str) or not _CIK.fullmatch(cik) for cik in scope["ciks"])
            or len(set(scope["ciks"])) != len(scope["ciks"])
            or not isinstance(scope["prior"], dict) or not set(scope["prior"]) <= set(scope["ciks"])):
        raise Blocked("Scope requires 1..1000 distinct zero-padded CIKs and explicit prior map")
    revisions = scope.get("revisions", {})
    if not isinstance(revisions, dict) or not set(revisions) <= set(scope["ciks"]):
        raise Blocked("Revision pins must name only selected CIKs")
    if set(support) != {"version", "ticker_manifest", "name_census", "bindings", "as_of"} or support["version"] != 1:
        raise Blocked("Company support must pin ticker, Name Census and reviewed binding fixtures")
    try:
        as_of = datetime.fromisoformat(support["as_of"].replace("Z", "+00:00"))
        if as_of.tzinfo is None:
            raise ValueError("as_of requires a timezone")
    except (AttributeError, TypeError, ValueError) as exc:
        raise Blocked("Company support must pin a timezone-aware as_of") from exc
    artifacts.verified(reference(support["ticker_manifest"]), max_bytes=256 * 1024**2)
    censuses = support["name_census"]
    if not isinstance(censuses, dict) or set(censuses) != set(scope["ciks"]):
        raise Blocked("Support must pin one Name Census fixture per bounded CIK")
    for cik in scope["ciks"]:
        artifacts.verified(reference(censuses[cik]), max_bytes=256 * 1024**2)
    if not isinstance(support["bindings"], dict) or set(support["bindings"]) != set(scope["ciks"]):
        raise Blocked("Support must pin a reviewed local binding per CIK")
    for cik in scope["ciks"]:
        artifacts.verified(reference(support["bindings"][cik]), max_bytes=1024 * 1024)
    main, expand, silver = [], [], []
    revision, capture_evidence, company_evidence, filing_evidence = [], [], [], []
    prepare_mdm, expand_publish = [], []
    for ordinal, cik in enumerate(scope["ciks"]):
        prior = scope["prior"].get(cik)
        if prior is not None:
            artifacts.verified(reference(prior))
        revision_pin = revisions.get(cik, {"revision": 0, "position": -1, "prior": None})
        if (not isinstance(revision_pin, dict)
                or set(revision_pin) != {"revision", "position", "prior"}
                or type(revision_pin["revision"]) is not int
                or type(revision_pin["position"]) is not int
                or revision_pin["revision"] < 0 or revision_pin["position"] < -1
                or (revision_pin["prior"] is None) != (revision_pin["position"] == -1)
                or (revision_pin["revision"] == 0) != (revision_pin["position"] == -1)):
            raise Blocked("Source revision must pin its prior position and evidence")
        if revision_pin["prior"] is not None:
            artifacts.verified(reference(revision_pin["prior"]))
        decision = _decision(cik=cik, file="main", cause=scope_ref, prior=prior)
        unit = _unit(cik, "main", decision, output_root, artifacts)
        main.append(unit)
        expand.append({"keys": {"cik": cik},
                       "input": {"from": {"step": "capture_main", "key": decision["request"]["candidate_id"]}},
                       "output": output_root.rstrip("/") + f"/expansion/{cik}.json",
                       "cursor": {"generated_step": "capture_page", "ordinal_base": ordinal * 128,
                                  "support": support_ref}})
        silver.append({"keys": {"cik": cik},
                       "input": {"from": {"step": "capture_main", "key": decision["request"]["candidate_id"]}},
                       "output": output_root.rstrip("/") + f"/landing/{cik}/manifest.json",
                       "cursor": {"support": support_ref}})
        for step, producer, source_step, source_key, bucket in (
            ("revision", "revision", "capture_main", decision["request"]["candidate_id"], revision),
            ("capture", "capture", "capture_main", decision["request"]["candidate_id"], capture_evidence),
            ("sec_company", "sec_company", "silver", cik, company_evidence),
            ("sec_company_filing", "sec_company_filing", "silver", cik, filing_evidence),
        ):
            bucket.append({"keys": {"cik": cik, "file": "main", "producer": producer,
                                    "journal_producer": "source.evidence",
                                    "journal_event_key": f"company/{cik}/{scope_ref['sha256']}/{producer}",
                                    "journal_event_type": "source.revision" if producer == "revision" else "producer.verified"},
                           "input": {"from": {"step": source_step, "key": source_key}},
                           "output": output_root.rstrip("/") + f"/evidence/{cik}/{producer}.json",
                           "cursor": {"company_evidence": producer, **(
                               {"resource_checkpoint": {"resource": f"source:{SOURCE}:{FEED}:{cik}",
                                                        "revision": revision_pin["revision"],
                                                        "position": revision_pin["position"]},
                                "prior_revision": revision_pin["prior"]}
                               if producer == "revision" else {})}})
        prepare_mdm.append({"keys": {"cik": cik},
                            "input": {"from": {"step": "silver", "key": cik}},
                            "output": output_root.rstrip("/") + f"/mdm-preparation/{cik}.json",
                            "cursor": {"support": support_ref, "generated_step": "ingest",
                                       "ordinal_base": ordinal,
                                       "publication_revision": revision_pin["position"] + 1}})
        expand_publish.append({"keys": {"cik": cik},
                               "input": {"from": {"step": "prepare_mdm", "key": cik}},
                               "output": output_root.rstrip("/") + f"/publication-expansion/{cik}.json",
                               "cursor": {"generated_step": "publish", "ordinal_base": ordinal * 3}})
    manifest = {"version": 2, "steps": {"capture_main": main, "expand_pages": expand,
                                         "capture_page": [], "revision": revision, "silver": silver,
                                         "capture": capture_evidence, "sec_company": company_evidence,
                                         "sec_company_filing": filing_evidence,
                                         "prepare_mdm": prepare_mdm, "ingest": [],
                                         "expand_publish": expand_publish, "publish": []}}
    return artifacts.put(output_root.rstrip("/") + "/inputs", manifest)


def register_company_expansion(registry):
    def expected(book, item):
        outcome = book.artifacts.json(item["unit"]["input"])
        if (outcome.get("source"), outcome.get("feed"), outcome.get("scope")) != (
                SOURCE, FEED, {"cik": item["unit"]["keys"]["cik"], "file": "main"}):
            raise Blocked("Expansion input is not this CIK's verified main capture")
        raw = book.artifacts.json(outcome["artifact"])
        if raw.get("cik") != int(item["unit"]["keys"]["cik"]):
            raise Blocked("Main payload CIK differs from frozen scope")
        filings = raw.get("filings")
        if not isinstance(filings, dict):
            raise Blocked("Main payload has no filing inventory")
        entries = filings.get("files", [])
        # source.evidence has a 128-reference ceiling: proof, main, pages,
        # snapshot and an optional prior revision must all fit.
        if not isinstance(entries, list) or len(entries) > 124:
            raise Blocked("Pagination scope exceeds its bound")
        names = [entry.get("name") for entry in entries if isinstance(entry, dict)]
        if len(names) != len(entries) or any(not isinstance(name, str) or not _PAGE.fullmatch(name)
                                            for name in names) or len(set(names)) != len(names):
            raise Blocked("Main payload has an invalid or repeated pagination file")
        cik = item["unit"]["keys"]["cik"]
        output_root = item["unit"]["output"].rsplit("/expansion/", 1)[0]
        cause = {"uri": item["unit"]["input"]["uri"],
                 "sha256": item["unit"]["input"]["sha256"]}
        children = [_unit(cik, name, _decision(cik=cik, file=name, cause=cause),
                          output_root, book.artifacts) for name in names]
        parent = {"step": item["step"], "key": item["unit_key"], "generated_step": "capture_page",
                  "ordinal_base": item["unit"]["cursor"]["ordinal_base"]}
        return {"version": 1, "parent": parent, "children": children}

    def verify(book, item, receipt):
        if not receipt or receipt.get("uri") != item["unit"]["output"]:
            return False
        ref = {"uri": receipt["uri"], "sha256": receipt["sha256"]}
        if receipt.get("evidence") != ref:
            return False
        actual = book.artifacts.json(ref)
        wanted = expected(book, item)
        _, config, _, _ = book._frozen(str(item["run_id"]))
        generated_worklist(actual, config, wanted["parent"])
        return actual == wanted

    def execute(book, item, authority):
        body = expected(book, item)
        ref = book.artifacts.put_bytes(item["unit"]["output"], canonical(body).encode())
        return {**ref, "evidence": ref}

    def reconcile(book, item, authority):
        try:
            data = book.artifacts.read(item["unit"]["output"])
        except Blocked:
            return None
        import hashlib
        ref = {"uri": item["unit"]["output"], "sha256": hashlib.sha256(data).hexdigest()}
        receipt = {**ref, "evidence": ref}
        if not verify(book, item, receipt):
            raise Blocked("Stored pagination expansion conflicts with main capture")
        return receipt

    registry.operation("company.expand", Capability("company-pagination-v1", execute, reconcile, verify))


_KEYS = {"sec_company": ["cik"], "sec_company_address": ["cik", "address_type"],
         "sec_company_filing": ["accession_number", "cik"],
         "sec_company_former_name": ["cik", "ordinal"],
         "sec_company_submission_file": ["cik", "file_name"]}
_REQUIRED = ("sec_company", "sec_company_address", "sec_company_filing",
             "sec_company_former_name")
_EMPTY_COLUMNS = {
    "sec_company_address": ("cik", "address_type", "street1", "street2", "city", "zip_code",
                            "state_or_country", "last_sync_run_id"),
    "sec_company_filing": ("accession_number", "cik", "form", "last_sync_run_id"),
    "sec_company_former_name": ("cik", "former_name", "ordinal", "last_sync_run_id"),
}


def register_company_silver(registry):
    import pyarrow as pa
    import pyarrow.parquet as pq
    from edgar_warehouse.serving.silver_landing_export import LandingExportBuffer
    from edgar_warehouse.silver_landing_store import SilverLandingStore

    def captures(book, item):
        cik = item["unit"]["keys"]["cik"]
        main = book.artifacts.json(item["unit"]["input"])
        if main.get("scope") != {"cik": cik, "file": "main"} or main.get("outcome") not in {"captured", "unchanged"}:
            raise Blocked("Silver requires a verified main capture")
        raw = book.artifacts.json(main["artifact"])
        with book.engine.connect() as conn:
            from sqlalchemy import text
            rows = conn.execute(text("SELECT unit_key,receipt,state FROM bookkeeping.work_item WHERE run_id=CAST(:r AS uuid) AND step='capture_page'"),
                                {"r": str(item["run_id"])}).mappings().all()
        pages = []
        for row in rows:
            if row["state"] != "verified" or not isinstance(row["receipt"], dict):
                raise Blocked("Silver waits for every pagination capture")
            outcome = book.artifacts.json({"uri": row["receipt"]["uri"], "sha256": row["receipt"]["sha256"]})
            if outcome.get("scope", {}).get("cik") == cik:
                page = outcome["scope"]["file"]
                if outcome.get("outcome") not in {"captured", "unchanged"}:
                    raise Blocked("Pagination page did not capture")
                pages.append((page, book.artifacts.json(outcome["artifact"])))
        filings = raw.get("filings")
        if not isinstance(filings, dict) or not isinstance(filings.get("files", []), list):
            raise Blocked("Main capture has no bounded pagination inventory")
        declared = [entry["name"] for entry in filings.get("files", [])]
        if set(declared) != {name for name, _ in pages} or len(declared) != len(pages):
            raise Blocked("Silver page set differs from sealed expansion")
        return main, raw, sorted(pages)

    def verify(book, item, receipt):
        if not receipt or receipt.get("uri") != item["unit"]["output"]:
            return False
        ref = {"uri": receipt["uri"], "sha256": receipt["sha256"]}
        if receipt.get("evidence") != ref:
            return False
        main, _, pages = captures(book, item)
        manifest = book.artifacts.json(ref)
        if (manifest.get("target") != "silver_landing" or manifest.get("schema_version") != 1
                or manifest.get("run_id") != str(item["run_id"])
                or manifest.get("cik") != item["unit"]["keys"]["cik"]
                or manifest.get("capture") != main["artifact"]
                or manifest.get("page_count") != len(pages)):
            return False
        found = {entry["table_name"]: entry for entry in manifest.get("tables", [])}
        if not set(_REQUIRED) <= set(found) or len(found) != len(manifest["tables"]):
            return False
        root = item["unit"]["output"].rsplit("/landing/", 1)[0] + "/landing/"
        for table, entry in found.items():
            if table not in _KEYS or entry.get("file_count") != 1:
                return False
            expected_uri = root + entry["relative_path"]
            data = book.artifacts.verified({"uri": expected_uri, "sha256": entry["sha256"]}, max_bytes=64 * 1024**2)
            rows = pq.read_table(pa.BufferReader(data)).to_pylist()
            if len(rows) != entry["row_count"]:
                return False
            identities = [tuple(row[field] for field in _KEYS[table]) for row in rows]
            if (len(set(identities)) != len(identities)
                    or digest(sorted(identities, key=canonical)) != entry["business_keys_sha256"]):
                return False
            if any(row.get("cik") != int(item["unit"]["keys"]["cik"]) for row in rows):
                return False
        return found["sec_company"]["row_count"] == 1

    def execute(book, item, authority):
        main, raw, pages = captures(book, item)
        buffer = LandingExportBuffer()
        silver = SilverLandingStore(landing_export=buffer)
        silver.stage_submission(cik=int(item["unit"]["keys"]["cik"]), main_payload=raw,
                                pagination_payloads=pages, sync_run_id=str(item["run_id"]),
                                raw_object_id=main["artifact"]["sha256"], load_mode="company")
        tables = buffer.tables()
        support = book.artifacts.json(item["unit"]["cursor"]["support"])
        observed_at = datetime.fromisoformat(support["as_of"].replace("Z", "+00:00"))
        for rows in tables.values():
            for row in rows:
                if "last_synced_at" in row:
                    row["last_synced_at"] = observed_at
        if len(tables.get("sec_company", [])) != 1:
            raise Blocked("Company parser produced no unique Company row")
        root = item["unit"]["output"].rsplit("/landing/", 1)[0] + "/landing/"
        cik = item["unit"]["keys"]["cik"]
        entries = []
        for table in sorted(set(tables) | set(_REQUIRED)):
            rows = tables.get(table, [])
            if table not in _KEYS:
                raise Blocked("Company parser produced an unexpected table")
            if rows:
                arrow = pa.Table.from_pylist(rows)
            else:
                arrow = pa.Table.from_pylist([], schema=pa.schema([
                    (key, pa.int64() if key in {"cik", "ordinal"} else pa.string())
                    for key in _EMPTY_COLUMNS[table]]))
            stream = pa.BufferOutputStream()
            pq.write_table(arrow, stream)
            relative = f"{cik}/{table}.parquet"
            data_ref = book.artifacts.put_bytes(root + relative, stream.getvalue().to_pybytes())
            identities = [tuple(row[field] for field in _KEYS[table]) for row in rows]
            if len(set(identities)) != len(identities):
                raise Blocked("Company Silver contains duplicate business keys")
            entries.append({"table_name": table, "relative_path": relative, "file_count": 1,
                            "row_count": len(rows), "sha256": data_ref["sha256"],
                            "business_keys_sha256": digest(sorted(identities, key=canonical))})
        manifest = {"schema_version": 1, "target": "silver_landing", "run_id": str(item["run_id"]),
                    "cik": cik, "capture": main["artifact"], "page_count": len(pages), "tables": entries}
        ref = book.artifacts.put_bytes(item["unit"]["output"], canonical(manifest).encode())
        receipt = {**ref, "evidence": ref}
        if not verify(book, item, receipt):
            raise Blocked("Silver landing readback failed")
        return receipt

    def reconcile(book, item, authority):
        try:
            data = book.artifacts.read(item["unit"]["output"])
        except Blocked:
            return None
        ref = {"uri": item["unit"]["output"], "sha256": hashlib.sha256(data).hexdigest()}
        receipt = {**ref, "evidence": ref}
        if not verify(book, item, receipt):
            raise Blocked("Existing Company Silver landing failed readback")
        return receipt

    registry.operation("company.silver", Capability("company-silver-landing-v1", execute, reconcile, verify))


def company_evidence_spec(book, item) -> dict:
    """Derive exact Journal producer evidence from a verified capture or landing."""
    producer = item["unit"]["cursor"]["company_evidence"]
    cik = item["unit"]["keys"]["cik"]
    scope = {"cik": cik, "file": "main"}
    input_ref = item["unit"]["input"]
    root = item["unit"]["output"].rsplit("/evidence/", 1)[0]
    if producer in {"revision", "capture"}:
        outcome = book.artifacts.json(input_ref)
        if outcome.get("scope") != scope or outcome.get("outcome") not in {"captured", "unchanged"}:
            raise Blocked("Capture producer has no matching main outcome")
        raw = reference(outcome["artifact"])
        main_body = book.artifacts.json(raw)
        filings = main_body.get("filings")
        if not isinstance(filings, dict):
            raise Blocked("Main capture has no filing inventory")
        declared = filings.get("files", [])
        if not isinstance(declared, list):
            raise Blocked("Main capture has no bounded pagination inventory")
        names = [entry.get("name") for entry in declared if isinstance(entry, dict)]
        if len(names) != len(declared) or len(set(names)) != len(names):
            raise Blocked("Main capture has invalid pagination names")
        from sqlalchemy import text
        with book.engine.connect() as conn:
            rows = conn.execute(text("""SELECT receipt,state,unit FROM bookkeeping.work_item
                WHERE run_id=CAST(:r AS uuid) AND step='capture_page'"""),
                {"r": str(item["run_id"])}).mappings().all()
        page_refs = {}
        for row in rows:
            if row["unit"]["keys"].get("cik") != cik:
                continue
            if row["state"] != "verified" or not isinstance(row["receipt"], dict):
                raise Blocked("Source revision waits for verified pages")
            page_outcome = book.artifacts.json({"uri": row["receipt"]["uri"],
                                                "sha256": row["receipt"]["sha256"]})
            page = page_outcome.get("scope", {}).get("file")
            if (page_outcome.get("source"), page_outcome.get("feed"),
                    page_outcome.get("scope", {}).get("cik")) != (SOURCE, FEED, cik):
                raise Blocked("Page outcome belongs to a different source scope")
            if page_outcome.get("outcome") not in {"captured", "unchanged"} or page in page_refs:
                raise Blocked("Page outcome is missing or duplicated")
            page_refs[page] = reference(page_outcome["artifact"])
        if set(page_refs) != set(names):
            raise Blocked("Source revision page set differs from main capture")
        snapshot = {"version": 1, "main_sha256": raw["sha256"],
                    "pages": [{"file": name, "sha256": page_refs[name]["sha256"]}
                              for name in names]}
        snapshot_ref = book.artifacts.put(root + "/snapshots", snapshot)
        members = [{"artifact": ref, "format": "bytes" if index == 0 else "page-bytes",
                    "count": 1, "key_fields": [],
                    "business_keys_sha256": digest([[ref["sha256"]] if index == 0
                                                    else [ref["uri"], ref["sha256"]]])}
                   for index, ref in enumerate([raw, *(page_refs[name] for name in names)])]
        count = len(members)
    elif producer in {"sec_company", "sec_company_filing"}:
        landing = book.artifacts.json(input_ref)
        if landing.get("cik") != cik or landing.get("run_id") != str(item["run_id"]):
            raise Blocked("Producer landing belongs to a different scope")
        landing_root = input_ref["uri"].rsplit("/landing/", 1)[0] + "/landing/"
        members = []
        for entry in landing["tables"]:
            table = entry["table_name"]
            if (producer == "sec_company_filing") != (table == "sec_company_filing"):
                continue
            members.append({"artifact": {"uri": landing_root + entry["relative_path"],
                                          "sha256": entry["sha256"]},
                            "format": "parquet", "count": entry["row_count"],
                            "key_fields": _KEYS[table],
                            "business_keys_sha256": entry["business_keys_sha256"]})
        if not members:
            raise Blocked("Required Company producer has no landing member")
        count = sum(member["count"] for member in members)
    else:
        raise Blocked("Unknown Company evidence producer")
    proof = {"version": 1, "kind": "scope.complete", "source": SOURCE, "feed": FEED,
             "scope": scope, "producer": "capture" if producer == "revision" else producer,
             "expected": count, "members": members}
    proof_ref = book.artifacts.put(root + "/scope-proofs", proof)
    evidence = [proof_ref, *[member["artifact"] for member in members]]
    if producer == "revision":
        checkpoint = item["unit"]["cursor"]["resource_checkpoint"]
        prior_revision = item["unit"]["cursor"]["prior_revision"]
        prior_body = book.artifacts.json(prior_revision)["body"] if prior_revision else None
        body = {"raw": raw, "canonical": snapshot_ref, "domain": snapshot_ref,
                "processing_versions": {"parser": "submissions-parser-v1", "schema": "silver-company-v1",
                                        "configuration": book._run(str(item["run_id"]))["submission"]["rule_version"]},
                "completeness": "full_snapshot", "scope_complete": proof_ref,
                "position": checkpoint["position"] + 1, "prior": prior_revision,
                "relationship": ("initial" if prior_body is None else
                                 "unchanged" if snapshot_ref["sha256"] == prior_body["domain"]["sha256"]
                                 else "changed")}
        evidence.append(snapshot_ref)
        if prior_revision:
            evidence.append(prior_revision)
        kind = "source.revision"
    else:
        body = {"producer": producer, "expected": count, "verified": count,
                "scope_complete": proof_ref}
        kind = "producer.verified"
    return {"version": 1, "kind": kind, "event_key": item["unit"]["keys"]["journal_event_key"],
            "source": SOURCE, "feed": FEED, "scope": scope, "evidence": evidence, "body": body}


def _local_path(uri: str) -> Path:
    parsed = urlparse(uri)
    if parsed.scheme != "file" or parsed.netloc:
        raise Blocked("Company MDM preparation currently requires local file evidence")
    return Path(unquote(parsed.path)).resolve()


def register_company_mdm_preparation(registry):
    from edgar_warehouse.mdm.clean.company_source import census_filers, prepare_company_bundle
    from edgar_warehouse.mdm.clean.name_census import sec_keys

    def build(book, item):
        cik = item["unit"]["keys"]["cik"]
        landing_ref = item["unit"]["input"]
        landing = book.artifacts.json(landing_ref)
        if landing.get("cik") != cik or landing.get("run_id") != str(item["run_id"]):
            raise Blocked("MDM preparation received a different Company landing")
        support = book.artifacts.json(item["unit"]["cursor"]["support"])
        ticker = reference(support["ticker_manifest"])
        census_ref = reference(support["name_census"][cik])
        book.artifacts.verified(ticker)
        template = book.artifacts.json(census_ref)
        landing_path = _local_path(landing_ref["uri"])
        landing_root = landing_path.parent.parent
        ticker_path = _local_path(ticker["uri"])
        if not ticker_path.is_relative_to(landing_root):
            raise Blocked("Ticker fixture must be under the pinned landing root")
        filers, population = census_filers(landing_root=str(landing_root),
                                           landing_manifest=str(landing_path))
        expected_keys = sec_keys(filers)
        entries = template.get("entries")
        if (not isinstance(entries, dict) or set(entries) != set(expected_keys)
                or any(entries[key].get("cik_count") != len(ciks)
                       or entries[key].get("ciks") != sorted(ciks)[:5]
                       for key, ciks in expected_keys.items())
                or template.get("sec", {}).get("filers") != len(filers)):
            raise Blocked("Pinned Name Census fixture disagrees with landed Company names")
        census = {**template, "sec": population}
        output_root = item["unit"]["output"].rsplit("/mdm-preparation/", 1)[0]
        census_uri = output_root + f"/census/{cik}.json"
        book.artifacts.put_bytes(census_uri, canonical(census).encode())
        bundle_dir = _local_path(output_root + f"/bundles/{cik}/{landing_ref['sha256']}")
        # The existing Company adapter validates all landing and support members.
        report = prepare_company_bundle(landing_root=str(landing_root),
            landing_manifest=str(landing_path), ticker_manifest=str(ticker_path),
            name_census=str(_local_path(census_uri)), output=str(bundle_dir),
            limit=1, as_of=support["as_of"],
            revision=item["unit"]["cursor"]["publication_revision"])
        manifest = book.artifacts.json({"uri": (bundle_dir / "manifest.json").as_uri(),
            "sha256": report["files"]["manifest.json"]["sha256"]})
        batch = manifest["batches"][0]
        record_ref = {"uri": (bundle_dir / "records.jsonl").as_uri(),
                      "sha256": batch["input"]["sha256"]}
        book.artifacts.verified(record_ref)
        binding = book.artifacts.json(reference(support["bindings"][cik]))
        try:
            if (set(binding) != {"version", "cik", "entity_id", "actor", "reason", "at"}
                    or binding["version"] != 1 or binding["cik"] != cik
                    or not binding["actor"] or not binding["reason"]):
                raise ValueError("Invalid reviewed binding fixture")
            UUID(binding["entity_id"])
        except (ValueError, KeyError, TypeError) as exc:
            raise Blocked("Reviewed binding fixture is invalid") from exc
        from edgar_warehouse.mdm.clean.adapters import normalize
        from edgar_warehouse.mdm.clean.evidence import decision
        contract = json.loads((bundle_dir / "dataset.json").read_text())
        policy = json.loads((bundle_dir / "policy.json").read_text())
        record = json.loads((bundle_dir / "records.jsonl").read_text())
        export = book.artifacts.json(book._run(str(item["run_id"]))["submission"]["rules"])
        reading = export["registration"]["datasets"][batch["input"]["source_code"]]
        assertion = normalize(record, source_code=batch["input"]["source_code"],
            contract=contract, mapping_version=reading["mapping_version"], policy=policy,
            publication={**batch["input"]["publication"], "artifact_sha256": record_ref["sha256"],
                         "member": record_ref["uri"],
                         "record_locator": f"{record_ref['sha256']}:line:1"})
        if assertion["kind"] != "company" or assertion["identifiers"].get("cik") != cik:
            raise Blocked("Reviewed binding is not for this Company's CIK")
        identity = {"entity_id": binding["entity_id"], "kind": "company",
                    "published_at": binding["at"]}
        bound = decision("bind", actor=binding["actor"], reason=binding["reason"],
            at=binding["at"], subject=assertion["subject"], entity_id=binding["entity_id"],
            evidence=[assertion["assertion_id"]])
        command = {"version": 1,
                   "source_input": {"source_code": batch["input"]["source_code"],
                                    "artifact": record_ref,
                                    "publication": batch["input"]["publication"],
                                    "record_count": batch["input"]["record_count"]},
                   "command": {"batch_id": batch["batch_id"], "consumer": batch["consumer"],
                               "expected_checkpoint": batch["expected_checkpoint"],
                               "checkpoint": batch["checkpoint"],
                               "policy_digest": manifest["policy_digest"],
                               "as_of": manifest["as_of"], "identities": [identity], "decisions": [bound]}}
        command_ref = book.artifacts.put(output_root + "/mdm-commands", command)
        parent = {"step": item["step"], "key": item["unit_key"],
                  "generated_step": "ingest", "ordinal_base": item["unit"]["cursor"]["ordinal_base"]}
        child = {"keys": {"batch_id": batch["batch_id"], "consumer": batch["consumer"]},
                 "input": command_ref, "output": output_root + f"/mdm-ingest/{cik}.json",
                 "cursor": {"bundle_manifest": (bundle_dir / "manifest.json").as_uri()}}
        return {"version": 1, "parent": parent, "children": [child]}

    def verify(book, item, receipt):
        if not receipt or receipt.get("uri") != item["unit"]["output"]:
            return False
        ref = {"uri": receipt["uri"], "sha256": receipt["sha256"]}
        if receipt.get("evidence") != ref:
            return False
        actual = book.artifacts.json(ref)
        wanted = build(book, item)
        _, config, _, _ = book._frozen(str(item["run_id"]))
        generated_worklist(actual, config, wanted["parent"])
        return actual == wanted

    def execute(book, item, authority):
        ref = book.artifacts.put_bytes(item["unit"]["output"], canonical(build(book, item)).encode())
        receipt = {**ref, "evidence": ref}
        if not verify(book, item, receipt):
            raise Blocked("MDM preparation failed immutable readback")
        return receipt

    def reconcile(book, item, authority):
        try:
            data = book.artifacts.read(item["unit"]["output"])
        except Blocked:
            return None
        ref = {"uri": item["unit"]["output"], "sha256": hashlib.sha256(data).hexdigest()}
        receipt = {**ref, "evidence": ref}
        if not verify(book, item, receipt):
            raise Blocked("Existing MDM preparation differs from pinned inputs")
        return receipt

    registry.operation("company.prepare", Capability("company-bundle-v1", execute, reconcile, verify))

    def publication_build(book, item):
        prepared = book.artifacts.json(item["unit"]["input"])
        if prepared.get("parent", {}).get("key") != item["unit"]["keys"]["cik"]:
            raise Blocked("Publication expansion received another Company bundle")
        command_ref = prepared["children"][0]["input"]
        command = book.artifacts.json(command_ref)["command"]
        output_root = item["unit"]["output"].rsplit("/publication-expansion/", 1)[0]
        batch_id = command["batch_id"]
        children = []
        for consumer, destination in (("journal", "change-journal"),
                                      ("export", output_root + "/publications/export"),
                                      ("graph", output_root + "/publications/graph")):
            spec = {"version": 1, "batch_id": batch_id, "consumer": consumer,
                    "destination": destination}
            ref = book.artifacts.put(output_root + "/publication-intents", spec)
            children.append({"keys": {"batch_id": batch_id, "consumer": consumer},
                             "input": ref, "output": output_root + f"/mdm-publish/{consumer}/{batch_id}.json",
                             "cursor": {}})
        parent = {"step": item["step"], "key": item["unit_key"],
                  "generated_step": "publish", "ordinal_base": item["unit"]["cursor"]["ordinal_base"]}
        return {"version": 1, "parent": parent, "children": children}

    def publish_verify(book, item, receipt):
        if not receipt or receipt.get("uri") != item["unit"]["output"]:
            return False
        ref = {"uri": receipt["uri"], "sha256": receipt["sha256"]}
        if receipt.get("evidence") != ref:
            return False
        actual = book.artifacts.json(ref)
        wanted = publication_build(book, item)
        _, config, _, _ = book._frozen(str(item["run_id"]))
        generated_worklist(actual, config, wanted["parent"])
        return actual == wanted

    def publish_execute(book, item, authority):
        ref = book.artifacts.put_bytes(item["unit"]["output"], canonical(publication_build(book, item)).encode())
        return {**ref, "evidence": ref}

    def publish_reconcile(book, item, authority):
        try:
            data = book.artifacts.read(item["unit"]["output"])
        except Blocked:
            return None
        ref = {"uri": item["unit"]["output"], "sha256": hashlib.sha256(data).hexdigest()}
        receipt = {**ref, "evidence": ref}
        if not publish_verify(book, item, receipt):
            raise Blocked("Publication expansion differs from committed MDM input")
        return receipt

    registry.operation("company.publish_expand", Capability("company-publications-v1",
        publish_execute, publish_reconcile, publish_verify))
