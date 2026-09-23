"""Authenticate native batch membership and account consumption in existing runs.

No new ledger: the frozen plan lives in PipelineRun.scope_json; each range and
its evidence commit in batch.effects with the existing family checkpoint.
"""

from __future__ import annotations

from collections import defaultdict

from .gleif_source import VERSION, record_evidence
from .source_publications import plan_continuity
from .store import Conflict, canonical, current_reading, digest, reading_at


def prepare_native(
    manifest, store, coordinator, verifier, *, observed, limit, run_id=None
):
    """Verify all source bytes before returning at most one invocation of evidence."""
    if verifier is None:
        raise Conflict(
            "Native consumption requires an acquisition publication verifier"
        )
    spec = manifest["native_source"]
    batches = manifest["batches"]
    if any(
        b["stage"] != "mastering"
        or "native_input" not in b
        or any(
            k in b
            for k in (
                "input",
                "assertions",
                "deferred",
                "continuity_proof",
                "source_family",
                "publication_family",
                "committed_publication",
            )
        )
        for b in batches
    ):
        raise Conflict("Native manifests require authenticated mastering ranges only")
    if len({b["consumer"] for b in batches}) != 1:
        raise Conflict("One native manifest must use one consumer")
    selected: dict = {}
    budget = 0
    for batch in batches:
        request = batch["native_input"]
        if (
            set(request) != {"publication", "member", "offset", "count"}
            or any(
                type(request[k]) is not int or request[k] < 0
                for k in ("offset", "count")
            )
            or request["count"] > 1000
        ):
            raise Conflict("Invalid bounded native range")
    for batch in batches:
        request = batch["native_input"]
        if batch["batch_id"] in observed:
            continue
        cost = max(1, request["count"])
        if budget + cost > limit:
            if not selected:
                raise ValueError(f"Next atomic batch requires --limit at least {cost}")
            break
        selected[batch["batch_id"]] = request
        budget += cost
    raw_rows: dict = defaultdict(list)
    by_member: dict = defaultdict(list)
    for key, req in selected.items():
        by_member[(req["publication"], req["member"])].append((key, req))
    retained_bytes = 0

    def retain(publication, member, row, ordinal):
        nonlocal retained_bytes
        for key, req in by_member[(publication, member)]:
            if req["offset"] <= ordinal < req["offset"] + req["count"]:
                retained_bytes += len(canonical(row).encode())
                if retained_bytes > 16 * 1024**2:
                    raise Conflict("Native invocation exceeds 16 MiB; partition ranges")
                raw_rows[key].append((ordinal, row))

    revisions = spec["publications"]
    if (
        not isinstance(revisions, list)
        or not 1 <= len(revisions) <= 128
        or len(set(revisions)) != len(revisions)
    ):
        raise Conflict("Supply 1..128 unique captured publication revisions")
    proofs = [
        verifier.verify(
            store,
            source_code=spec["source_code"],
            manifest_revision_id=r,
            on_native_record=retain,
        )
        for r in revisions
    ]
    if any(
        p.evidence.get("native_contract", {}).get("version") != VERSION for p in proofs
    ):
        raise Conflict("Native consumer requires registered native source contracts")
    previous = None
    if spec.get("previous_run_id"):
        prior = coordinator.completed_source(spec["previous_run_id"])
        if prior["consumer"] != batches[0]["consumer"]:
            raise Conflict("Predecessor was consumed by a different consumer")
        saved = prior["plan"]["publications"][-1]
        previous = verifier.verify(
            store,
            source_code=spec["source_code"],
            manifest_revision_id=saved["evidence"]["manifest_revision_id"],
        )
        if previous.proof_digest != saved["proof_digest"]:
            raise Conflict("Previously consumed source proof changed")
    plan = plan_continuity(
        proofs, target_sequence=spec["target_sequence"], previous=previous
    )
    if spec.get("plan_digest", plan["proof_digest"]) != plan["proof_digest"]:
        raise Conflict("Pinned native recovery plan changed")
    planned = {p["evidence"]["publication"]: p for p in plan["publications"]}
    predecessor = previous.evidence if previous else None
    for proof in plan["publications"]:
        current = proof["evidence"]
        if current["mode"] == "delta":
            if predecessor is None:
                raise Conflict("Native delta lacks a consumed/full predecessor")
            old_members = {m["member"]: m for m in predecessor["members"]}
            from .evidence import instant

            if any(
                instant(m["native"]["delta_start"])
                != instant(old_members[m["member"]]["native"]["content_date"])
                for m in current["members"]
            ):
                raise Conflict("Native delta start does not match predecessor content")
        predecessor = current
    native = plan["publications"][0]["evidence"]["native_contract"]
    # A run resumes under the readings it started with. Reading the newest on
    # every invocation put the current mapping digest into the reconstructed
    # run scope, so registering a corrected mapping mid-run made the run
    # unresumable with "Root run scope changed" (Codex review of PR #695, P1).
    pinned = coordinator.pinned_readings(run_id) if run_id else {}
    with store.engine.connect() as conn:
        readings = {
            code: (
                reading_at(conn, code, pinned[code])
                if code in pinned
                else current_reading(conn, code)
            )
            for code in native["record_sources"].values()
        }
    if any(r is None for r in readings.values()):
        raise Conflict("Native record datasets must be registered before consumption")
    # Each source is read under its own mapping, and every record says which
    # reading produced it (ticket 01, decision 4).
    contracts = {code: r[1] for code, r in readings.items()}
    mapping_versions = {code: r[0] for code, r in readings.items()}
    for member, code in native["record_sources"].items():
        contract = contracts[code]
        adapter = contract.get("adapter", {})
        if (
            adapter.get("native_member") != member
            or adapter.get("version") != VERSION
            or contract.get("schema_version") != VERSION
            or contract.get("family")
            != plan["publications"][0]["evidence"]["source_family"]
        ):
            raise Conflict(
                "Native record dataset interpretation does not match its member"
            )
    expected, spans = {}, defaultdict(list)
    for batch in batches:
        req = batch["native_input"]
        if (
            req["publication"] not in planned
            or req["member"] not in native["record_sources"]
        ):
            raise Conflict("Batch is outside the selected native recovery plan")
        proof = planned[req["publication"]]
        code = native["record_sources"][req["member"]]
        expected[batch["batch_id"]] = {
            "version": 1,
            "plan_digest": plan["proof_digest"],
            "publication_proof_digest": proof["proof_digest"],
            "source_code": code,
            "record_dataset_digest": digest(contracts[code]),
            **req,
        }
        spans[(req["publication"], req["member"])].append((req["offset"], req["count"]))
    # Prove complete, nonoverlapping coverage before registering a root run.
    for publication, proof in planned.items():
        for member in proof["evidence"]["members"]:
            intervals = sorted(spans[(publication, member["member"])])
            total = member["native"]["record_count"]
            if total == 0:
                if intervals != [(0, 0)]:
                    raise Conflict(
                        "Empty native member requires exactly one accounted range"
                    )
                continue
            position = 0
            for offset, count in intervals:
                if offset != position or count == 0:
                    raise Conflict("Native range gap or overlap")
                position += count
            if position != total:
                raise Conflict(
                    "Native manifest does not account for the whole publication"
                )
    publication_order = {
        p["evidence"]["publication"]: i for i, p in enumerate(plan["publications"])
    }
    order = [publication_order[b["native_input"]["publication"]] for b in batches]
    if order != sorted(order):
        raise Conflict(
            "Native publication batches must follow the frozen recovery plan"
        )
    prepared = {}
    eligible_leis = set(native["company_leis"])
    for key, req in selected.items():
        proof = planned[req["publication"]]
        doc = proof["evidence"]
        member = next(m for m in doc["members"] if m["member"] == req["member"])
        if len(raw_rows[key]) != req["count"]:
            raise Conflict("Native batch records were not authenticated")
        evidence: dict = {"assertion": [], "deferred": []}
        code = expected[key]["source_code"]
        for ordinal, row in raw_rows[key]:
            kind, body = record_evidence(
                row,
                member=req["member"],
                contract=contracts[code],
                source_code=code,
                eligible_leis=eligible_leis,
                ordinal=ordinal,
                mapping_version=mapping_versions[code],
                publication={
                    "publication_key": doc["publication"],
                    "revision": doc["sequence"],
                    "artifact_sha256": member["raw_evidence_hash"],
                    "member": req["member"],
                },
            )
            evidence[kind].append(body)
        prepared[key] = {
            "assertions": evidence["assertion"],
            "deferred": evidence["deferred"],
            "source_family": doc["source_family"],
            "publication_family": doc["publication_family"],
            "committed_publication": doc["publication"],
            "continuity_proof": expected[key],
        }
    return {
        "version": 1,
        "consumer": batches[0]["consumer"],
        "plan": plan,
        "batches": expected,
        # Pinned so a resume resolves these readings rather than whatever has
        # been registered since. Without them the scope carries the newest
        # mapping's digest and cannot be reproduced on a second invocation.
        "mapping_versions": mapping_versions,
    }, prepared


def consumption_report(scope, effects):
    """Derive completion from actual committed evidence, not checkpoint position."""
    missing, invalid = [], []
    for key, expected in scope["batches"].items():
        body = effects.get(key)
        if body is None:
            missing.append(key)
            continue
        a, d = body["normalized"], body["deferred"]
        if (
            body.get("continuity_proof") != expected
            or a + d != expected["count"]
            or body.get("source_accounting")
            != {"normalized": a, "deferred": d, "total": a + d}
            or not body["source_consistent"]
        ):
            invalid.append(key)
    return {
        "source_delivery_verified": True,
        "source_consumption_complete": not missing and not invalid,
        "source_missing_batches": sorted(missing),
        "source_invalid_batches": sorted(invalid),
        "source_plan_digest": scope["plan"]["proof_digest"],
    }
