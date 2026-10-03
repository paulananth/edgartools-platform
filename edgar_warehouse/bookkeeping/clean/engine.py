"""Control for configured work: no worker code, no domain callbacks.

Workers and verifiers run in their own processes. They pull a task envelope,
report a candidate, and a verifier reports its checks; Bookkeeping admits a
report only against the envelope's bindings and the live lease (mastering
to-do 20a, after Codex's design of 2026-10-02).
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass
from datetime import UTC
from uuid import uuid4, uuid5, UUID

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from .artifacts import Artifacts
from .config import (RUN_CHECKS, STEP_CHECKS, Blocked, canonical, digest, generated_worklist, reference,
                     validate, worklist)

PROTOCOL = 1


@dataclass(frozen=True)
class Claim:
    run_id: str
    step: str
    key: str
    attempt: str
    proof: list[dict]


def _rows(conn, sql, **params):
    return [dict(row) for row in conn.execute(text(sql), params).mappings()]


class Bookkeeping:
    def __init__(self, engine, artifacts: Artifacts | None = None):
        self.engine = engine
        self.artifacts = artifacts or Artifacts()
        self.additional_engines = []

    def close(self):
        for engine in self.additional_engines:
            engine.dispose()
        self.engine.dispose()

    def _call(self, sql: str, **params):
        with self.engine.begin() as conn:
            return conn.scalar(text(sql), params)

    def _run(self, run_id: str) -> dict:
        with self.engine.connect() as conn:
            result = _rows(conn, "SELECT * FROM bookkeeping.pipeline_run WHERE run_id=CAST(:r AS uuid)", r=run_id)
        if not result:
            raise Blocked("Unknown run; legacy runs cannot be resumed")
        return result[0]

    def _frozen(self, run_id: str):
        run = self._run(run_id)
        if run["submission"].get("journal") != "change-journal-v1" or run["submission"].get("protocol") != PROTOCOL:
            raise Blocked("Legacy runs and deliveries must finish on their original stack")
        try:
            submission = run["submission"]
            if digest(submission) != run["submission_hash"]:
                raise Blocked("Frozen submission hash mismatch")
            export = self.artifacts.json(submission["rules"])
            if digest(export["body"]) != export["digest"]:
                raise Blocked("Rules document hash mismatch")
            if (export["kind"], export["name"], export["version"]) != (
                    submission["kind"], submission["name"], submission["rule_version"]):
                raise Blocked("Rules reference disagrees with submission")
            if "acquisition" in export["body"]:
                from edgar_warehouse.rules.acquisition_authority import frozen_authority
                frozen_authority(export, submission["scope"].get("feed"), artifacts=self.artifacts)
            config = validate(export["body"], submission["target"])
            manifest = self.artifacts.json(submission["inputs"])
            items = worklist(manifest, config)
            if digest(items) != submission["worklist_hash"]:
                raise Blocked("Frozen work accounting changed")
            with self.engine.connect() as conn:
                stored = _rows(conn, "SELECT step,unit_key,ordinal,resources,unit,receipt,state,generated_count FROM bookkeeping.work_item WHERE run_id=CAST(:r AS uuid)", r=run_id)
            expected = {(entry["step"], entry["key"]): entry for entry in items}
            for row in stored:
                cursor = row["unit"].get("cursor")
                marker = cursor.get("generated_step") if isinstance(cursor, dict) else None
                if marker is None or row["state"] != "verified":
                    continue
                if row["generated_count"] is None:
                    raise Blocked("Expansion completed without sealing generated scope")
                receipt = row["receipt"]
                if not isinstance(receipt, dict):
                    raise Blocked("Verified expansion has no immutable receipt")
                expansion = self.artifacts.json({"uri": receipt["uri"], "sha256": receipt["sha256"]})
                parent = {"step": row["step"], "key": row["unit_key"], "generated_step": marker,
                          "ordinal_base": cursor.get("ordinal_base")}
                for child in generated_worklist(expansion, config, parent):
                    identity = (child["step"], child["key"])
                    if identity in expected:
                        raise Blocked("Generated work repeats frozen or earlier work")
                    expected[identity] = child
                    items.append(child)
                if len(expansion["children"]) != row["generated_count"]:
                    raise Blocked("Sealed expansion count differs from immutable children")
            if len(expected) != run["expected_count"] or len(stored) != len(expected):
                raise Blocked("Generated work accounting changed")
            for row in stored:
                item = expected.get((row["step"], row["unit_key"]))
                if (item is None or row["ordinal"] != item["ordinal"]
                        or row["resources"] != item["resources"] or row["unit"] != item["unit"]):
                    raise Blocked("Stored work differs from frozen or generated manifest")
            return run, config, manifest, items
        except (Blocked, KeyError, TypeError) as exc:
            self._call("SELECT bookkeeping.block_run(CAST(:r AS uuid),:m)", r=run_id, m=str(exc))
            if isinstance(exc, Blocked):
                raise
            raise Blocked("Corrupt frozen submission") from exc

    def start(self, *, rules_ref: dict, inputs_ref: dict, target: str, scope: dict,
              run_id: str | None = None) -> str:
        """Called with an active Rules resolver export, never a mutable YAML file."""
        reference(rules_ref)
        reference(inputs_ref)
        export = self.artifacts.json(rules_ref)
        proof = export.get("proof")
        from edgar_warehouse.rules.acquisition_authority import proof_holds

        if (export.get("status") != "active" or not isinstance(proof, dict) or not proof_holds(export)
                or digest(export["body"]) != export.get("digest")):
            raise Blocked("Submission requires a proven active Rules export")
        reference({"uri": rules_ref["uri"], "sha256": proof.get("batch_hash")})
        config = validate(export["body"], target)
        if scope.get("feed") and "acquisition" not in export["body"]:
            raise Blocked("Retired acquisition feed cannot be submitted")
        if "acquisition" in export["body"]:
            from edgar_warehouse.rules.acquisition_authority import frozen_authority
            selected = frozen_authority(export, scope.get("feed"), artifacts=self.artifacts)
            if scope.get("source") != export["name"]:
                raise Blocked("Acquisition run requires exact source/feed binding")
            if not set(selected["configuration"]["required_producers"]) <= {s["name"] for s in config["steps"]}:
                raise Blocked("Configured work omits required acquisition producers")
        # An approval is pinned to the exact immutable body, including its
        # Bookkeeping section. No automatic approval from an earlier version.
        if export["kind"] == "merge" or export["body"].get("mdm") or target == "mdm":
            approval = export.get("approval") or {}
            if approval.get("digest") != export["digest"] or not approval.get("by") or not approval.get("at"):
                raise Blocked("MDM configuration requires approval of its exact digest")
        manifest = self.artifacts.json(inputs_ref)
        items = worklist(manifest, config)
        if "acquisition" in export["body"] and not items:
            raise Blocked("An empty acquisition baseline requires explicit verified scope work")
        submission = {"version": 1, "kind": export["kind"], "name": export["name"],
                      "journal": "change-journal-v1", "protocol": PROTOCOL,
                      "rule_version": export["version"], "rules": rules_ref, "inputs": inputs_ref,
                      "target": target, "scope": scope, "worklist_hash": digest(items)}
        run_id = run_id or str(uuid4())
        self._call("SELECT bookkeeping.start_run(CAST(:r AS uuid),CAST(:s AS jsonb),:h,CAST(:i AS jsonb))",
                   r=run_id, s=canonical(submission), h=digest(submission), i=canonical(items))
        return run_id

    def claim(self, run_id: str, step_name: str, key: str, *, sleep=time.sleep) -> Claim | None:
        _, config, _, _ = self._frozen(run_id)
        step = next((s for s in config["steps"] if s["name"] == step_name), None)
        if step is None:
            raise Blocked("Unknown step")
        retry = config["retry"]
        attempt = str(uuid4())
        for n in range(retry["attempts"]):
            try:
                proof = self._call("SELECT bookkeeping.claim(CAST(:r AS uuid),:s,:k,CAST(:a AS uuid),:d,CAST(:p AS jsonb))",
                                   r=run_id, s=step_name, k=key, a=attempt, d=config["lease_seconds"], p=canonical(step["requires"]))
                if proof is None:
                    return None
                return Claim(run_id, step_name, key, attempt, proof)
            except DBAPIError as exc:
                if getattr(exc.orig, "pgcode", None) != "55P03":
                    raise
                if n + 1 < retry["attempts"]:
                    sleep(random.uniform(0, min(retry["cap_ms"], retry["base_ms"] * 2 ** n)) / 1000)
        self._call("SELECT bookkeeping.wait_work(CAST(:r AS uuid),:s,:k,:m,NULL,'[]'::jsonb)",
                   r=run_id, s=step_name, k=key, m="Lease or prerequisite contention; retry on resume")
        return None

    def heartbeat(self, claim: Claim) -> Claim:
        _, config, _, _ = self._frozen(claim.run_id)
        proof = self._call("SELECT bookkeeping.heartbeat(CAST(:r AS uuid),:s,:k,CAST(:a AS uuid),CAST(:p AS jsonb),:d)",
                           r=claim.run_id, s=claim.step, k=claim.key, a=claim.attempt, p=canonical(claim.proof), d=config["lease_seconds"])
        return Claim(claim.run_id, claim.step, claim.key, claim.attempt, proof)

    def item(self, claim: Claim) -> dict:
        with self.engine.connect() as conn:
            found = _rows(conn, "SELECT * FROM bookkeeping.work_item WHERE run_id=CAST(:r AS uuid) AND step=:s AND unit_key=:k",
                          r=claim.run_id, s=claim.step, k=claim.key)
        if not found:
            raise Blocked("Unknown unit")
        return self._resolve_item(found[0])

    def _resolve_item(self, item: dict, *, context: dict | None = None) -> dict:
        """Materialize an input from immutable, reverified prerequisite evidence.

        The stored unit retains the frozen selector. Capabilities receive an
        ordinary URI/hash, so their business interface and versions stay the
        same. A missing receipt never triggers upstream discovery or replay.
        """
        source = item["unit"]["input"]
        if "from" not in source:
            return item
        if context is None:
            run, config, manifest, _ = self._frozen(str(item["run_id"]))
            context = {"run": run, "config": config, "manifest": manifest}
        dependency = source["from"]
        with self.engine.connect() as conn:
            found = _rows(conn, """SELECT * FROM bookkeeping.work_item
                WHERE run_id=CAST(:r AS uuid) AND step=:s AND unit_key=:k AND state='verified'""",
                r=str(item["run_id"]), s=dependency["step"], k=dependency["key"])
        if not found:
            raise Blocked("Prerequisite input lacks verified completion")
        upstream = self._resolve_item(found[0], context=context)
        self._verify_item(upstream, context)
        receipt = upstream["receipt"]
        resolved = reference({"uri": receipt["uri"], "sha256": receipt["sha256"]})
        self.artifacts.verified(resolved)
        return {**item, "unit": {**item["unit"], "input": resolved}}

    def _row(self, run_id: str, step: str, key: str) -> dict:
        with self.engine.connect() as conn:
            found = _rows(conn, "SELECT * FROM bookkeeping.work_item WHERE run_id=CAST(:r AS uuid) AND step=:s AND unit_key=:k",
                          r=run_id, s=step, k=key)
        if not found:
            raise Blocked("Unknown unit")
        return found[0]

    def _verify_item(self, item: dict, context: dict):
        """Recheck retained completion evidence: the candidate's bytes, and a
        verifier report bound to exactly this work and candidate. Control
        reads no destination; the verifier did, when it reported."""
        step = next(s for s in context["config"]["steps"] if s["name"] == item["step"])
        receipt = item["receipt"]
        if not isinstance(receipt, dict) or set(receipt) != {"uri", "sha256", "evidence"}:
            raise Blocked("Prerequisite completion receipt is missing or malformed")
        candidate = {"uri": receipt["uri"], "sha256": receipt["sha256"]}
        self.artifacts.verified(reference(candidate))
        report = self.artifacts.json(receipt["evidence"])
        binding = report.get("binding") if isinstance(report.get("binding"), dict) else {}
        if (report.get("protocol") != PROTOCOL or binding.get("candidate") != candidate
                or (binding.get("run_id"), binding.get("step"), binding.get("key"))
                != (str(item["run_id"]), item["step"], item["unit_key"])):
            raise Blocked("Previously completed evidence is no longer valid")
        if any(item["checks"].get(name) is not True for name in step["checks"]):
            raise Blocked("Previously completed checks no longer pass")

    def check(self, run_id: str) -> dict:
        """The run's own checks; control computes every one of them."""
        run, config, _, _ = self._frozen(run_id)
        status = self.status(run_id)
        results = {}
        for name in config["checks"]:
            if name == "manifest.hash":
                self.artifacts.verified(run["submission"]["inputs"])
                results[name] = True
            elif name == "work.accounting":
                results[name] = status["counts"].get("verified", 0) == run["expected_count"]
            elif name == "journal.delivered":
                results[name] = status["pending_deliveries"] == 0
            else:
                raise Blocked(f"Unsupported run check: {name}")
        return results

    # The task protocol. A worker pulls an envelope, renews it while it works
    # and reports a candidate; a separate verifier reads the destination and
    # reports its checks. Nothing here imports, names or calls a worker.

    def envelope(self, claim: Claim) -> dict:
        """Everything a worker may know: the frozen work, its live authority
        and the domain checks its verifier must report. No connection, no
        engine, no private method crosses this boundary."""
        run, config, _, _ = self._frozen(claim.run_id)
        step = next(s for s in config["steps"] if s["name"] == claim.step)
        row = self._row(claim.run_id, claim.step, claim.key)
        item = self._resolve_item(row)
        rules = run["submission"]["rules"]
        return {"protocol": PROTOCOL, "profile": step["operation"],
                "claim": {"run_id": claim.run_id, "step": claim.step, "key": claim.key,
                          "attempt": claim.attempt, "proof": claim.proof},
                # One logical effect across retries; a new input, rules
                # version or output is new work with a new key.
                "effect_key": digest({"rules": rules, "step": claim.step, "key": claim.key, "unit": row["unit"]}),
                "rules": rules, "input": item["unit"]["input"], "output": item["unit"]["output"],
                "keys": row["unit"]["keys"], "cursor": row["unit"]["cursor"],
                "checks": [name for name in step["checks"] if name not in STEP_CHECKS],
                "heartbeat_seconds": config["heartbeat_seconds"], "retry": config["retry"],
                "deadline": min(str(p["expires_at"]) for p in claim.proof)}

    @staticmethod
    def _claim_of(envelope: dict) -> Claim:
        try:
            if envelope["protocol"] != PROTOCOL:
                raise Blocked("Unsupported task protocol")
            c = envelope["claim"]
            return Claim(c["run_id"], c["step"], c["key"], c["attempt"], c["proof"])
        except (KeyError, TypeError) as exc:
            raise Blocked("Malformed task envelope") from exc

    def _same_work(self, envelope: dict, claim: Claim) -> dict:
        current = self.envelope(claim)
        if {k: v for k, v in envelope.items() if k not in ("claim", "candidate", "deadline")} != {
                k: v for k, v in current.items() if k not in ("claim", "deadline")}:
            raise Blocked("Envelope differs from the frozen work")
        return current

    def tasks(self, run_id: str, profile: str, *, limit: int = 10) -> list[dict]:
        """Claim up to `limit` units of a profile's steps, in step order. A unit
        another attempt holds under a live lease is skipped, not contended."""
        if not 1 <= limit <= 1000:
            raise ValueError("Task limit must be 1..1000")
        _, config, _, _ = self._frozen(run_id)
        found = []
        for step in config["steps"]:
            if step["operation"] != profile or len(found) >= limit:
                continue
            with self.engine.connect() as conn:
                # A reported unit belongs to verifiers, never to another worker.
                keys = conn.scalars(text("""SELECT unit_key FROM bookkeeping.work_item w
                    WHERE run_id=CAST(:r AS uuid) AND step=:s AND state NOT IN ('verified','reported')
                    AND NOT EXISTS(SELECT 1 FROM bookkeeping.lease l WHERE l.run_id=w.run_id
                        AND l.attempt=w.attempt AND l.expires_at>clock_timestamp())
                    ORDER BY ordinal LIMIT :n"""), {"r": run_id, "s": step["name"], "n": limit - len(found)}).all()
            for key in keys:
                claim = self.claim(run_id, step["name"], key, sleep=lambda _: None)
                if claim is None:
                    continue
                try:
                    found.append(self.envelope(claim))
                except (Blocked, KeyError, TypeError) as exc:
                    # Corrupt or missing prerequisite evidence: no work starts on it.
                    self._call("SELECT bookkeeping.block_run(CAST(:r AS uuid),:m)", r=run_id, m=str(exc))
                    raise Blocked(str(exc)) from exc
        return found

    def renew(self, envelope: dict) -> dict:
        return {**envelope, "claim": {**envelope["claim"], "proof": self.heartbeat(self._claim_of(envelope)).proof}}

    def report(self, envelope: dict, candidate: dict, runtime: str) -> dict:
        """A worker's candidate; the unit is not complete until verified."""
        claim = self._claim_of(envelope)
        reference(candidate)
        current = self._same_work(envelope, claim)
        if candidate["uri"] != current["output"]:
            raise Blocked("A candidate must be written to the work's intended output")
        self._call("SELECT bookkeeping.report(CAST(:r AS uuid),:s,:k,CAST(:a AS uuid),CAST(:p AS jsonb),CAST(:c AS jsonb),:f,:t)",
                   r=claim.run_id, s=claim.step, k=claim.key, a=claim.attempt, p=canonical(claim.proof),
                   c=canonical({"uri": candidate["uri"], "sha256": candidate["sha256"]}), f=current["profile"], t=runtime)
        return {"reported": candidate, "step": claim.step, "key": claim.key}

    def fail(self, envelope: dict, message: str) -> None:
        """Give up this attempt; the unit waits for a later claim."""
        self.wait(self._claim_of(envelope), message[:200])

    def verifications(self, run_id: str, profile: str, *, limit: int = 10) -> list[dict]:
        """Reported candidates of a profile's steps. The verifier works under
        the reporting attempt's leases, renewed or re-taken here; a unit whose
        resource another attempt holds is skipped."""
        if not 1 <= limit <= 1000:
            raise ValueError("Verification limit must be 1..1000")
        _, config, _, _ = self._frozen(run_id)
        steps = [s["name"] for s in config["steps"] if s["operation"] == profile]
        with self.engine.connect() as conn:
            rows = _rows(conn, """SELECT step,unit_key,attempt,candidate FROM bookkeeping.work_item
                WHERE run_id=CAST(:r AS uuid) AND step = ANY(:s) AND state='reported'
                ORDER BY step,ordinal LIMIT :n""", r=run_id, s=steps, n=limit)
        found = []
        for row in rows:
            try:
                proof = self._call("SELECT bookkeeping.verify_claim(CAST(:r AS uuid),:s,:k,CAST(:a AS uuid),:d)",
                                   r=run_id, s=row["step"], k=row["unit_key"], a=str(row["attempt"]),
                                   d=config["lease_seconds"])
            except DBAPIError as exc:
                if getattr(exc.orig, "pgcode", None) != "55P03":
                    raise
                continue
            if proof:
                claim = Claim(run_id, row["step"], row["unit_key"], str(row["attempt"]), proof)
                found.append({**self.envelope(claim), "candidate": row["candidate"]})
        return found

    def admit(self, verification: dict, report_ref: dict) -> dict:
        """Complete a unit from a verifier's report: every binding, the
        required checks and the live lease must hold. Worker success alone
        is never enough."""
        claim = self._claim_of(verification)
        reference(report_ref)
        run, config, _, _ = self._frozen(claim.run_id)
        step = next(s for s in config["steps"] if s["name"] == claim.step)
        current = self._same_work(verification, claim)
        row = self._row(claim.run_id, claim.step, claim.key)
        if row["state"] == "verified" and str(row["attempt"]) == claim.attempt:
            # A lost acknowledgement: the same report is admitted again; any
            # other report for completed work is a conflict.
            if row["receipt"] != {"uri": verification.get("candidate", {}).get("uri"),
                                  "sha256": verification.get("candidate", {}).get("sha256"), "evidence": report_ref}:
                raise Blocked("Completion evidence changed")
            return {"verified": verification["candidate"], "step": claim.step, "key": claim.key}
        if row["state"] != "reported" or str(row["attempt"]) != claim.attempt or row["candidate"] != verification.get("candidate"):
            raise Blocked("Only the live attempt's reported candidate can be verified")
        candidate = row["candidate"]
        report = self.artifacts.json(report_ref)
        binding = {"run_id": claim.run_id, "step": claim.step, "key": claim.key, "attempt": claim.attempt,
                   "effect_key": verification["effect_key"], "candidate": candidate}
        if set(report) != {"protocol", "binding", "checks", "proofs", "runtime"} or report["protocol"] != PROTOCOL:
            raise Blocked("Malformed verification report")
        if report["binding"] != binding:
            raise Blocked("Verification report names other work")
        required = set(step["checks"]) - STEP_CHECKS
        reported = report["checks"]
        if not isinstance(reported, dict) or set(reported) != required or any(v is not True for v in reported.values()):
            raise Blocked("Verification report lacks a required check")
        if not isinstance(report["proofs"], list):
            raise Blocked("Malformed verification report")
        for proof in report["proofs"]:
            self.artifacts.verified(reference(proof))
        self._call("SELECT bookkeeping.pin_verifier(CAST(:r AS uuid),:f,:t)",
                   r=claim.run_id, f=step["operation"], t=report["runtime"])
        receipt = {"uri": candidate["uri"], "sha256": candidate["sha256"], "evidence": report_ref}
        checks = dict(reported)
        if "input.hash" in step["checks"]:
            self.artifacts.verified(current["input"])
            checks["input.hash"] = True
        if "output.receipt" in step["checks"]:
            self.artifacts.verified(candidate)
            checks["output.receipt"] = True
        self._complete(claim, config, row, receipt, checks)
        return {"verified": candidate, "step": claim.step, "key": claim.key}

    def _complete(self, claim: Claim, config: dict, row: dict, receipt: dict, checks: dict) -> None:
        event_id = str(uuid5(UUID(claim.run_id), f"{claim.step}:{claim.key}"))
        parameters = dict(r=claim.run_id, s=claim.step, k=claim.key, a=claim.attempt,
                          p=canonical(claim.proof), v=canonical(receipt), c=canonical(checks), e=event_id)
        cursor = row["unit"]["cursor"]
        checkpoint = cursor.get("resource_checkpoint") if isinstance(cursor, dict) else None
        generated_step = cursor.get("generated_step") if isinstance(cursor, dict) else None
        if generated_step is not None:
            expansion = self.artifacts.json({"uri": receipt["uri"], "sha256": receipt["sha256"]})
            children = generated_worklist(expansion, config, {"step": claim.step, "key": claim.key,
                                                              "generated_step": generated_step,
                                                              "ordinal_base": cursor.get("ordinal_base")})
            self._call("SELECT bookkeeping.finish_expand(CAST(:r AS uuid),:s,:k,CAST(:a AS uuid),CAST(:p AS jsonb),CAST(:v AS jsonb),CAST(:c AS jsonb),CAST(:e AS uuid),CAST(:children AS jsonb),:child_step)",
                       **parameters, children=canonical(children), child_step=generated_step)
        elif checkpoint is not None:
            self._call("SELECT bookkeeping.finish_resource(CAST(:r AS uuid),:s,:k,CAST(:a AS uuid),CAST(:p AS jsonb),CAST(:v AS jsonb),CAST(:c AS jsonb),CAST(:e AS uuid),:resource,:revision,:position)",
                       **parameters, **checkpoint)
        else:
            self._call("SELECT bookkeeping.finish(CAST(:r AS uuid),:s,:k,CAST(:a AS uuid),CAST(:p AS jsonb),CAST(:v AS jsonb),CAST(:c AS jsonb),CAST(:e AS uuid))", **parameters)

    def resource_checkpoint(self, resource: str) -> dict | None:
        with self.engine.connect() as conn:
            found = _rows(conn, "SELECT * FROM bookkeeping.checkpoint WHERE resource=:p", p=resource)
        return found[0] if found else None

    def wait(self, claim: Claim, message: str):
        self._call("SELECT bookkeeping.wait_work(CAST(:r AS uuid),:s,:k,:m,CAST(:a AS uuid),CAST(:p AS jsonb))",
                   r=claim.run_id, s=claim.step, k=claim.key, m=message, a=claim.attempt, p=canonical(claim.proof))

    def _verify_completed(self, run_id: str, config: dict):
        # Reverify retained receipts before skipping anything. If evidence is
        # corrupt, execution blocks; it never silently repeats committed work.
        with self.engine.connect() as conn:
            items = _rows(conn, "SELECT * FROM bookkeeping.work_item WHERE run_id=CAST(:r AS uuid) AND state='verified' ORDER BY step,ordinal", r=run_id)
        try:
            run, _, manifest, _ = self._frozen(run_id)
            context = {"run": run, "config": config, "manifest": manifest}
            for item in items:
                self._verify_item(self._resolve_item(item, context=context), context)
        except (Blocked, KeyError, TypeError) as exc:
            self._call("SELECT bookkeeping.block_run(CAST(:r AS uuid),:m)", r=run_id, m=str(exc))
            raise Blocked(str(exc)) from exc

    def resume(self, run_id: str) -> dict:
        run, config, _, _ = self._frozen(run_id)
        if run["compacted_at"]:
            raise Blocked("Compacted runs are audit-only; start a new run")
        self._verify_completed(run_id, config)
        self._call("SELECT bookkeeping.resume_run(CAST(:r AS uuid))", r=run_id)
        return self.status(run_id)

    def status(self, run_id: str, *, limit: int = 100) -> dict:
        if not 1 <= limit <= 1000:
            raise ValueError("status limit must be 1..1000")
        with self.engine.connect() as conn:
            items = _rows(conn, "SELECT step,unit_key,ordinal,state,attempt,attempts,receipt,checks,error FROM bookkeeping.work_item WHERE run_id=CAST(:r AS uuid) ORDER BY step,ordinal LIMIT :n", r=run_id, n=limit)
            counts = _rows(conn, "SELECT state,count(*) AS count FROM bookkeeping.work_item WHERE run_id=CAST(:r AS uuid) GROUP BY state", r=run_id)
            checkpoints = _rows(conn, "SELECT * FROM bookkeeping.checkpoint WHERE run_id=CAST(:r AS uuid)", r=run_id)
            leases = _rows(conn, "SELECT * FROM bookkeeping.lease WHERE run_id=CAST(:r AS uuid) ORDER BY resource LIMIT :n", r=run_id, n=limit)
            pending = conn.scalar(text("SELECT count(*) FROM bookkeeping.journal_outbox WHERE run_id=CAST(:r AS uuid) AND delivered_at IS NULL"), {"r": run_id})
            deliveries = _rows(conn, "SELECT event_id,step,unit_key,attempts,error,delivered_at FROM bookkeeping.journal_outbox WHERE run_id=CAST(:r AS uuid) ORDER BY delivered_at NULLS FIRST,created_at LIMIT :n", r=run_id, n=limit)
        return {"run": self._run(run_id), "items": items, "counts": {i["state"]: i["count"] for i in counts},
                "checkpoints": checkpoints, "leases": leases, "pending_deliveries": pending, "deliveries": deliveries}

    def runs(self, *, limit: int = 100, state: str | None = None) -> list[dict]:
        """Bounded discovery after a lost submission acknowledgement."""
        if not 1 <= limit <= 1000 or state not in (None, "running", "waiting", "blocked", "complete"):
            raise ValueError("Run listing requires a valid state and limit in 1..1000")
        with self.engine.connect() as conn:
            return _rows(conn, """SELECT run_id,state,created_at,completed_at,expected_count,summary,
                submission->>'kind' AS kind,submission->>'name' AS name,submission->>'target' AS target
                FROM bookkeeping.pipeline_run WHERE CAST(:s AS text) IS NULL OR state=:s
                ORDER BY created_at DESC,run_id LIMIT :n""", s=state, n=limit)

    def finalize(self, run_id: str) -> dict:
        run, config, _, _ = self._frozen(run_id)
        if run["compacted_at"]:
            return self.status(run_id)
        self._verify_completed(run_id, config)
        checks = self.check(run_id)
        self._call("SELECT bookkeeping.record_checks(CAST(:r AS uuid),CAST(:c AS jsonb))", r=run_id, c=canonical(checks))
        return self.status(run_id)

    def journal_event(self, event: dict) -> dict:
        """Control's one lifecycle event. Domain events (an acquisition's
        authorization, a publication) go through their worker's own Journal
        intent, never through a branch here."""
        from edgar_warehouse.change_journal import envelope
        if event.get("event_type", "work.verified") != "work.verified":
            raise Blocked("Bookkeeping emits only its lifecycle event")
        run, _, _, _ = self._frozen(str(event["run_id"]))
        submission = run["submission"]
        document = self.artifacts.json(submission["rules"])["body"]
        scope = submission["scope"]
        return envelope(producer="bookkeeping", event_key=str(event["event_id"]),
                        run_id=str(event["run_id"]), source=document.get("source", submission["name"]),
                        feed=scope.get("feed", document.get("bronze", {}).get("family", submission["target"])),
                        event_type="work.verified", occurred_at=event["created_at"].astimezone(UTC).isoformat(),
                        scope={"step": event["step"], "unit_key": event["unit_key"], "target": submission["target"]},
                        evidence=[event["payload"]["receipt"]["evidence"],
                                  {"uri": f"bookkeeping-outbox:///{event['event_id']}", "sha256": digest(event["payload"])}])

    def deliver(self, journal, run_id: str, *, limit: int = 100) -> int:
        if not 1 <= limit <= 1000:
            raise ValueError("delivery limit must be 1..1000")
        self._frozen(run_id)
        with self.engine.connect() as conn:
            events = _rows(conn, "SELECT * FROM bookkeeping.journal_outbox WHERE run_id=CAST(:r AS uuid) AND delivered_at IS NULL ORDER BY created_at,event_id LIMIT :n", r=run_id, n=limit)
        delivered = 0
        for event in events:
            try:
                # Separate DB transaction. Duplicate delivery reconciles the
                # exact envelope before acknowledging intent in Bookkeeping.
                receipt = journal.append(self.journal_event(event))
                journal.verify(receipt, expected=self.journal_event(event))
                self._call("SELECT bookkeeping.delivery(CAST(:e AS uuid),NULL)", e=str(event["event_id"]))
                delivered += 1
            except Exception as exc:
                self._call("SELECT bookkeeping.delivery(CAST(:e AS uuid),:m)", e=str(event["event_id"]), m=type(exc).__name__)
                raise
        return delivered
