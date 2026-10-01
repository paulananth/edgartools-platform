"""Common bounded MDM command capability; no source-specific control callbacks."""
from __future__ import annotations

from sqlalchemy import text

from .config import Blocked, Capability, canonical


def register_mdm(registry, mdm_engine, *, publisher_factory=None):
    """Bind the existing Merge Stage and its authoritative commit receipts.

    Input is an immutable prepared Merge Stage command, with source records
    left in the artifact. Bookkeeping stores only the artifact reference and
    compact batch/generation evidence. New source names require no changes.
    """
    from edgar_warehouse.mdm.clean.merge import MergeStage
    from edgar_warehouse.mdm.clean.quality import counts as quality_counts
    from edgar_warehouse.mdm.clean.store import Store

    def command(book, item):
        body = book.artifacts.json(item["unit"]["input"])
        if (set(body) not in ({"version", "command"}, {"version", "command", "source_input"})
                or type(body["version"]) is not int or body["version"] != 1
                or not isinstance(body["command"], dict)
                or set(body["command"]) & {"run_id", "preview", "lease_proof"}):
            raise Blocked("MDM input requires an immutable command without execution authority")
        submission = book._run(str(item["run_id"]))["submission"]
        export = book.artifacts.json(submission["rules"])
        step = next(step for step in export["body"]["bookkeeping"]["targets"][submission["target"]]["steps"]
                    if step["name"] == item["step"])
        expected = {"mdm.merge": {"version", "command"},
                    "mdm.ingest": {"version", "command", "source_input"}}[step["operation"]]
        if set(body) != expected:
            raise Blocked("MDM input shape differs from its configured capability")
        batch = body["command"]
        if "source_input" in body:
            from .source_input import normalize_input

            if set(batch) & {"assertions", "deferred", "occurrences"}:
                raise Blocked("Source input cannot mix generated and prepared evidence")
            batch = {**batch, **normalize_input(book, body["source_input"], export, mdm_engine, batch["policy_digest"])}
        if (not isinstance(batch.get("consumer"), str) or not batch["consumer"]
                or f"mdm:consumer:{batch['consumer']}" not in item["resources"]
                or any(item["unit"]["keys"].get(key, batch.get(key)) != batch.get(key)
                       for key in ("consumer", "batch_id"))):
            raise Blocked("MDM work does not own the consumer named by its immutable command")
        declared = export["body"].get("mdm")
        if declared:
            readings = (export.get("registration") or {}).get("datasets", {})
            for record in batch.get("assertions", []):
                code = record.get("source_code")
                if code not in declared or code not in readings or record.get("mapping_version", 1) != readings[code]["mapping_version"]:
                    raise Blocked("Prepared record differs from the source reading frozen by Rules")
            for record in batch.get("deferred", []):
                code = record.get("source_code")
                adapter = declared.get(code, {}).get("contract", {}).get("adapter", {})
                if (code not in declared or code not in readings
                        or adapter.get("version") != record.get("provenance", {}).get("adapter_version")):
                    raise Blocked("Deferred record differs from the source adapter frozen by Rules")
        return batch

    def observation(book, item):
        batch = command(book, item)
        with mdm_engine.connect() as conn:
            row = conn.execute(text("SELECT b.batch_id,b.generation,b.request_hash FROM mdm.batch b JOIN mdm.run_batch o USING(batch_id) WHERE o.run_id=CAST(:r AS uuid) AND b.batch_id=:b"),
                               {"r": str(item["run_id"]), "b": batch["batch_id"]}).mappings().first()
        if row is None:
            return None
        # Reuse Merge Stage's own immutable command comparison, including its
        # sorted assertions/decisions and deferred-record compatibility rules.
        result = MergeStage(Store(mdm_engine)).apply(**batch, run_id=str(item["run_id"]), preview=True)
        if not result.get("duplicate"):
            raise Blocked("Committed MDM batch did not reconcile")
        # What the data quality rule did to this batch's records, per fix and check.
        quality = quality_counts(batch.get("assertions", []), batch.get("deferred", []))
        return {"version": 1, "run_id": str(item["run_id"]), "batch_id": row["batch_id"],
                "generation": row["generation"], "request_hash": row["request_hash"],
                "input": item["unit"]["input"], **({"quality": quality} if quality else {})}

    def receipt(book, item, body):
        ref = book.artifacts.put_bytes(item["unit"]["output"], canonical(body).encode())
        return {**ref, "evidence": ref}

    def execute(book, item, authority):
        batch = command(book, item)
        MergeStage(Store(mdm_engine, lease_authority=authority)).apply(**batch, run_id=str(item["run_id"]))
        observed = observation(book, item)
        if observed is None:
            raise Blocked("MDM acknowledgement lacks commit evidence")
        return receipt(book, item, observed)

    def reconcile(book, item, authority):
        observed = observation(book, item)
        return None if observed is None else receipt(book, item, observed)

    def verify(book, item, found):
        if not found or found.get("uri") != item["unit"]["output"]:
            return False
        observed = observation(book, item)
        return observed is not None and book.artifacts.json(found["evidence"]) == observed

    def publication_verified(book, context):
        if "item" in context:
            units = [context["item"]["unit"]]
        else:
            if context["status"]["counts"].get("verified", 0) != context["run"]["expected_count"]:
                return False
            _, config, _, items = book._frozen(str(context["run"]["run_id"]))
            stages = {s["name"] for s in config["steps"] if s["operation"].startswith("mdm.")}
            units = [book._resolve_item({**item, "run_id": context["run"]["run_id"]})["unit"]
                     for item in items if item["step"] in stages]
            if not units and items:
                return False
        for unit in units:
            body = book.artifacts.json(unit["input"])
            key = body.get("batch_id") or body.get("command", {}).get("batch_id")
            with mdm_engine.connect() as conn:
                # Check the exact required consumer set, not merely zero
                # pending rows in a possibly incomplete set of intents.
                row = conn.execute(text("""SELECT p.body->'required_consumers' AS required,
                  (SELECT jsonb_agg(q.consumer ORDER BY q.consumer) FROM mdm.outbox q WHERE q.batch_id=b.batch_id) AS actual,
                  (SELECT count(*) FROM mdm.outbox q WHERE q.batch_id=b.batch_id AND q.verified_at IS NULL) AS pending
                  FROM mdm.batch b JOIN mdm.policy p ON p.digest=b.policy_digest WHERE b.batch_id=:b"""), {"b": key}).mappings().first()
            if row is None or sorted(row["required"]) != (row["actual"] or []) or row["pending"] != 0:
                return False
        return True

    registry.operation("mdm.merge", Capability("merge-stage-v1", execute, reconcile, verify))
    registry.operation("mdm.ingest", Capability("frozen-source-input-v1", execute, reconcile, verify))
    registry.check("mdm.publication", publication_verified)

    if publisher_factory is None:
        return

    def publication(book, item):
        spec = book.artifacts.json(item["unit"]["input"])
        if (set(spec) != {"version", "batch_id", "consumer", "destination"} or type(spec["version"]) is not int or spec["version"] != 1
                or any(not isinstance(spec[key], str) or not spec[key] for key in ("batch_id", "consumer", "destination"))):
            raise Blocked("Publication requires exact batch, consumer and destination intent")
        if (f"mdm:publication:{spec['consumer']}" not in item["resources"]
                or any(item["unit"]["keys"].get(key, spec[key]) != spec[key] for key in ("batch_id", "consumer"))):
            raise Blocked("Publication work does not own its configured consumer")
        with mdm_engine.connect() as conn:
            row = conn.execute(text("SELECT * FROM mdm.outbox WHERE batch_id=:b AND consumer=:c"),
                               {"b": spec["batch_id"], "c": spec["consumer"]}).mappings().first()
        if row is None:
            raise Blocked("Required publication intent is missing")
        return spec, row

    def published_receipt(book, item):
        spec, row = publication(book, item)
        if row["verified_at"] is None:
            return None
        sink = publisher_factory(spec)
        actual = sink.verify(f"{spec['consumer']}/{spec['batch_id']}", row["payload"], row["payload_hash"])
        if actual != row["payload_hash"]:
            raise Blocked("Publication read-back differs from intent")
        return receipt(book, item, {"version": 1, "batch_id": spec["batch_id"], "consumer": spec["consumer"],
                                    "payload_hash": actual, "destination": spec["destination"]})

    def publish_execute(book, item, authority):
        spec, _ = publication(book, item)
        store = Store(mdm_engine, lease_authority=authority)
        store.deliver_one(spec["consumer"], authority.current().attempt, publisher_factory(spec),
                          batch_id=spec["batch_id"], lease_seconds=120)
        found = published_receipt(book, item)
        if found is None:
            raise RuntimeError("Publication waits for an earlier generation or an existing fence")
        return found

    def publish_reconcile(book, item, authority):
        return published_receipt(book, item)

    def publish_verify(book, item, found):
        retained = published_receipt(book, item)
        return retained is not None and retained == found

    registry.operation("mdm.publish", Capability("mdm-publication-v1", publish_execute, publish_reconcile, publish_verify))
