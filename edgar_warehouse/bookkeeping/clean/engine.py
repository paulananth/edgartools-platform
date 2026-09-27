"""One interface for all configured control work; no source-name dispatch."""
from __future__ import annotations

import random
import time
from dataclasses import dataclass
from uuid import uuid4, uuid5, UUID

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from .artifacts import Artifacts
from .config import Blocked, Registry, canonical, digest, validate, worklist, reference


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
    def __init__(self, engine, registry: Registry, artifacts: Artifacts | None = None):
        self.engine, self.registry = engine, registry
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
            config = validate(export["body"], submission["target"], self.registry)
            versions = {step["operation"]: self.registry.operations[step["operation"]].version for step in config["steps"]}
            if versions != submission["processing_versions"]:
                raise Blocked("Processing versions changed; start a new run")
            manifest = self.artifacts.json(submission["inputs"])
            items = worklist(manifest, config)
            if len(items) != run["expected_count"] or digest(items) != submission["worklist_hash"]:
                raise Blocked("Frozen work accounting changed")
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
        if (export.get("status") != "active" or not isinstance(proof, dict)
                or proof.get("passed") is not True or proof.get("digest") != export.get("digest")
                or digest(export["body"]) != export.get("digest")):
            raise Blocked("Submission requires a proven active Rules export")
        reference({"uri": rules_ref["uri"], "sha256": proof.get("batch_hash")})
        config = validate(export["body"], target, self.registry)
        # An approval is pinned to the exact immutable body, including its
        # Bookkeeping section. No automatic approval from an earlier version.
        if (export["kind"] == "merge" or export["body"].get("mdm") or target == "mdm"
                or any(step["operation"] in {"mdm.merge", "mdm.ingest"} for step in config["steps"])):
            approval = export.get("approval") or {}
            if approval.get("digest") != export["digest"] or not approval.get("by") or not approval.get("at"):
                raise Blocked("MDM configuration requires approval of its exact digest")
        manifest = self.artifacts.json(inputs_ref)
        items = worklist(manifest, config)
        submission = {"version": 1, "kind": export["kind"], "name": export["name"],
                      "rule_version": export["version"], "rules": rules_ref, "inputs": inputs_ref,
                      "target": target, "scope": scope, "worklist_hash": digest(items),
                      "processing_versions": {s["operation"]: self.registry.operations[s["operation"]].version for s in config["steps"]}}
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
        return found[0]

    def check(self, run_id: str, *, claim: Claim | None = None, receipt: dict | None = None) -> dict:
        run, config, manifest, _ = self._frozen(run_id)
        if claim:
            step = next(s for s in config["steps"] if s["name"] == claim.step)
            names = step["checks"]
            context = {"run": run, "config": config, "manifest": manifest, "item": self.item(claim), "receipt": receipt}
        else:
            names = config["checks"]
            context = {"run": run, "config": config, "manifest": manifest, "status": self.status(run_id)}
        return {name: self.registry.checks[name](self, context) is True for name in names}

    def record_verified_completion(self, claim: Claim, receipt: dict) -> None:
        if not isinstance(receipt, dict) or set(receipt) != {"uri", "sha256", "evidence"}:
            raise Blocked("Completion retains receipt references only")
        _, config, _, _ = self._frozen(claim.run_id)
        step = next(s for s in config["steps"] if s["name"] == claim.step)
        capability = self.registry.operations[step["operation"]]
        item = self.item(claim)
        if capability.verify(self, item, receipt) is not True:
            raise Blocked("Destination completion evidence is invalid")
        reference({k: receipt[k] for k in ("uri", "sha256")})
        reference(receipt["evidence"])
        self.artifacts.verified(receipt["evidence"])
        checks = self.check(claim.run_id, claim=claim, receipt=receipt)
        if not checks or not all(checks.values()):
            raise Blocked("Required checks failed")
        event_id = str(uuid5(UUID(claim.run_id), f"{claim.step}:{claim.key}"))
        self._call("SELECT bookkeeping.finish(CAST(:r AS uuid),:s,:k,CAST(:a AS uuid),CAST(:p AS jsonb),CAST(:v AS jsonb),CAST(:c AS jsonb),CAST(:e AS uuid))",
                   r=claim.run_id, s=claim.step, k=claim.key, a=claim.attempt, p=canonical(claim.proof), v=canonical(receipt), c=canonical(checks), e=event_id)

    def wait(self, claim: Claim, message: str):
        self._call("SELECT bookkeeping.wait_work(CAST(:r AS uuid),:s,:k,:m,CAST(:a AS uuid),CAST(:p AS jsonb))",
                   r=claim.run_id, s=claim.step, k=claim.key, m=message, a=claim.attempt, p=canonical(claim.proof))

    def _verify_completed(self, run_id: str, config: dict):
        # Reverify retained receipts before skipping anything. If evidence is
        # corrupt, execution blocks; it never silently repeats committed work.
        with self.engine.connect() as conn:
            items = _rows(conn, "SELECT * FROM bookkeeping.work_item WHERE run_id=CAST(:r AS uuid) AND state='verified' ORDER BY step,ordinal", r=run_id)
        try:
            for item in items:
                step = next(s for s in config["steps"] if s["name"] == item["step"])
                receipt = item["receipt"]
                self.artifacts.verified(receipt["evidence"])
                if self.registry.operations[step["operation"]].verify(self, item, receipt) is not True:
                    raise Blocked("Previously completed evidence is no longer valid")
                context = {"run": self._run(run_id), "config": config, "item": item, "receipt": receipt}
                if not all(self.registry.checks[name](self, context) is True for name in step["checks"]):
                    raise Blocked("Previously completed checks no longer pass")
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

    def deliver(self, ledger, run_id: str, *, limit: int = 100) -> int:
        if not 1 <= limit <= 1000:
            raise ValueError("delivery limit must be 1..1000")
        with self.engine.connect() as conn:
            events = _rows(conn, "SELECT * FROM bookkeeping.journal_outbox WHERE run_id=CAST(:r AS uuid) AND delivered_at IS NULL ORDER BY created_at,event_id LIMIT :n", r=run_id, n=limit)
        delivered = 0
        for event in events:
            try:
                # Separate DB transaction. Duplicate delivery reconciles the
                # exact envelope before acknowledging intent in Bookkeeping.
                ledger.deliver(str(event["event_id"]), event["payload"])
                self._call("SELECT bookkeeping.delivery(CAST(:e AS uuid),NULL)", e=str(event["event_id"]))
                delivered += 1
            except Exception as exc:
                self._call("SELECT bookkeeping.delivery(CAST(:e AS uuid),:m)", e=str(event["event_id"]), m=type(exc).__name__)
                raise
        return delivered
