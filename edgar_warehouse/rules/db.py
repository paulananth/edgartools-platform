"""Single Rules version table, shared resolver/export boundary for Bookkeeping.

Files remain the authoring surface. This module does not add a second mapping
store or make workers read mutable authoring files.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

from sqlalchemy import create_engine, text

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.bookkeeping.clean.config import Blocked, canonical, digest
from . import files


APPROVAL_COLUMNS = "approved_by,approved_at,approved_words,approval_overrule,approval_evidence,approval_recorded_by"


def get_engine(url=None):
    return create_engine(url or os.environ["RULES_DATABASE_URL"], pool_pre_ping=True)


def migrate(engine, *, agent_role: str = "rules_agent", approver_role: str = "rules_approver"):
    if approver_role != "rules_approver":
        raise ValueError("Approval membership must be rules_approver")
    paths = sorted((Path(__file__).parent / "migrations").glob("[0-9]*.sql"))
    base_checksum = hashlib.sha256(paths[0].read_bytes()).hexdigest()
    quote = engine.dialect.identifier_preparer.quote
    with engine.begin() as conn:
        if conn.scalar(text("SELECT current_database()")) != "rules" or int(conn.scalar(text("SHOW server_version_num"))) // 10000 != 16:
            raise Blocked("Rules migration requires its own rules database on PostgreSQL 16")
        role = conn.execute(text("SELECT rolsuper,rolcreatedb,rolcreaterole FROM pg_roles WHERE rolname=:r"), {"r": agent_role}).first()
        if not role or any(role) or conn.scalar(text("SELECT current_user")) == agent_role:
            raise Blocked("Restricted Rules agent and separate migration owner required")
        if not conn.scalar(text("SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='rules_approver')")):
            raise Blocked("Create the rules_approver membership role explicitly")
        conn.execute(text("SELECT pg_advisory_xact_lock(730503)"))
        exists = conn.scalar(text("SELECT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname='rules')"))
        prior = conn.scalar(text("SELECT obj_description(oid,'pg_namespace') FROM pg_namespace WHERE nspname='rules'"))
        if exists and not prior:
            raise Blocked("Refusing to adopt an untracked Rules schema")
        # Version 1 stored its single checksum directly in the schema comment.
        try:
            checksums = {paths[0].name: prior} if prior == base_checksum else json.loads(prior) if prior else {}
        except ValueError as exc:
            raise Blocked("Rules migration checksum differs") from exc
        if not isinstance(checksums, dict) or set(checksums) - {p.name for p in paths}:
            raise Blocked("Rules migration history differs from this build")
        for path in paths:
            source = path.read_text()
            checksum = hashlib.sha256(source.encode()).hexdigest()
            if path.name in checksums:
                if checksums[path.name] != checksum:
                    raise Blocked("Rules migration checksum differs")
            else:
                conn.execute(text(source))
                checksums[path.name] = checksum
        comment = canonical(checksums).replace("'", "''")
        conn.exec_driver_sql(f"COMMENT ON SCHEMA rules IS '{comment}'")
        agent = quote(agent_role)
        conn.exec_driver_sql(f"REVOKE ALL ON ALL TABLES IN SCHEMA rules FROM PUBLIC,{agent},rules_approver")
        conn.exec_driver_sql(f"GRANT USAGE ON SCHEMA rules TO {agent},rules_approver")
        conn.exec_driver_sql(f"GRANT SELECT ON rules.rule_version TO {agent},rules_approver")
        conn.exec_driver_sql(f"GRANT INSERT(kind,name,version,body,digest) ON rules.rule_version TO {agent}")
        conn.exec_driver_sql(f"GRANT UPDATE(status,proof,batch_hash,clean_mdm) ON rules.rule_version TO {agent}")
        # The agent records the operator's approval in their name and words
        # (operator, 2026-09-29, rules skill ticket 14); the trigger refuses
        # one without test evidence or without those words.
        conn.exec_driver_sql(f"GRANT UPDATE({APPROVAL_COLUMNS}) ON rules.rule_version TO {agent},rules_approver")
        if conn.scalar(text("SELECT has_schema_privilege(:r,'rules','CREATE')"), {"r": agent_role}):
            raise Blocked("Rules agent owns the Rules schema")
    return checksums


def proof_holds(export: dict) -> bool:
    """A version's test evidence stands: its proof passed, or the operator
    overruled a failing one when approving this exact version."""
    proof, approval = export.get("proof") or {}, export.get("approval") or {}
    if proof.get("digest") != export.get("digest"):
        return False
    return proof.get("passed") is True or (
        proof.get("passed") is False and approval.get("digest") == export.get("digest") and bool(approval.get("overrule")))


class Rules:
    def __init__(self, engine):
        self.engine = engine

    def save(self, kind: str, name: str, version: str, body: dict) -> dict:
        if (kind not in ("source", "merge", "pipeline") or not isinstance(name, str) or not isinstance(version, str)
                or not re.fullmatch(r"[a-z][a-z0-9_.-]*", name) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", version)):
            raise Blocked("A supported document kind, name and version are required")
        if "acquisition" in body:
            from edgar_warehouse.change_journal.authority import acquisition
            acquisition(body)
        with self.engine.begin() as conn:
            conn.execute(text("INSERT INTO rules.rule_version(kind,name,version,body,digest) VALUES(:k,:n,:v,:b,:d) ON CONFLICT DO NOTHING"),
                         {"k": kind, "n": name, "v": version, "b": canonical(body), "d": digest(body)})
            row = self._version(conn, kind, name, version)
            if row["digest"] != digest(body) or row["body"] != canonical(body):
                raise Blocked("The version label already names different immutable content")
        return row

    @staticmethod
    def _version(conn, kind, name, version):
        row = conn.execute(text("SELECT * FROM rules.rule_version WHERE kind=:k AND name=:n AND version=:v"), {"k": kind, "n": name, "v": version}).mappings().first()
        if row is None:
            raise Blocked("Unknown Rules version")
        return dict(row)

    def version(self, kind, name, version):
        with self.engine.connect() as conn:
            return self._version(conn, kind, name, version)

    def prove(self, kind, name, version, proof):
        """Record a test run of this version, passing or not. A passing one
        makes it proven; a failing one stays a draft with its evidence, which
        the operator may overrule on approval (and a new run may replace)."""
        if type(proof.get("passed")) is not bool:
            raise Blocked("A proof says whether it passed")
        row = self.version(kind, name, version)
        body = json.loads(row["body"])
        if "acquisition" in body:
            from edgar_warehouse.change_journal.authority import validation_proof
            validation_proof(body, proof, artifacts=Artifacts())
        with self.engine.begin() as conn:
            conn.execute(text("UPDATE rules.rule_version SET status=:s,proof=CAST(:p AS jsonb),batch_hash=:h WHERE kind=:k AND name=:n AND version=:v"),
                         {"s": "proven" if proof["passed"] else "draft", "p": canonical(proof), "h": proof["batch_hash"],
                          "k": kind, "n": name, "v": version})

    def pending(self) -> list[dict]:
        """Every version with a recorded test run and no approval yet, newest
        first, with its evidence and what it changes from the active one."""
        with self.engine.connect() as conn:
            waiting = [dict(r) for r in conn.execute(text(
                "SELECT * FROM rules.rule_version WHERE proof IS NOT NULL AND approved_by IS NULL "
                "AND status IN ('draft','proven') ORDER BY kind,name,proved_at DESC")).mappings()]
            active = {(r["kind"], r["name"]): json.loads(r["body"]) for r in conn.execute(text(
                "SELECT kind,name,body FROM rules.rule_version WHERE status='active'")).mappings()}
        return [{"kind": r["kind"], "name": r["name"], "version": r["version"], "passed": r["proof"]["passed"],
                 "evidence": r["proof"].get("evidence"), "note": r["proof"].get("note"), "proved_at": r["proved_at"],
                 "changes": changes(active.get((r["kind"], r["name"])), json.loads(r["body"]))} for r in waiting]

    def approve(self, kind, name, version=None, *, by: str, words: str, overrule: str | None = None) -> dict:
        """Record the operator's approval, in their name and exact words, of the
        version with the newest test run (or the one named). No approval without
        test evidence; a failing run only with an overrule reason."""
        with self.engine.begin() as conn:
            if version is None:
                version = conn.scalar(text(
                    "SELECT version FROM rules.rule_version WHERE kind=:k AND name=:n AND proof IS NOT NULL "
                    "AND approved_by IS NULL AND status IN ('draft','proven') ORDER BY proved_at DESC LIMIT 1"),
                    {"k": kind, "n": name})
                if version is None:
                    raise Blocked(f"No version of {kind} {name} has test evidence waiting for approval")
            row = self._version(conn, kind, name, version)
            if row["proof"] is None:
                raise Blocked("No approval without test evidence: record a test run first")
            if row["proof"]["passed"] is False and not (overrule or "").strip():
                raise Blocked("The test run failed: approving it needs an overrule reason")
            conn.execute(text("UPDATE rules.rule_version SET approved_by=:by,approved_words=:w,approval_overrule=:o,"
                              "approved_at=clock_timestamp(),status='proven' WHERE kind=:k AND name=:n AND version=:v"),
                         {"by": by, "w": words, "o": overrule or None, "k": kind, "n": name, "v": version})
            return self._version(conn, kind, name, version)

    def activate(self, kind, name, version, *, mdm_engine=None):
        with self.engine.begin() as conn:
            # Serializes lifecycle changes for this document, not every source.
            conn.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:k,0))"), {"k": f"{kind}:{name}"})
            selected = self._version(conn, kind, name, version)
            if selected["status"] == "active":
                return
            if selected["status"] != "proven":
                raise Blocked("Only a proven version can activate")
            body = json.loads(selected["body"])
            if "acquisition" in body:
                from edgar_warehouse.change_journal.authority import validation_proof
                validation_proof(body, selected["proof"], artifacts=Artifacts())
            requires_handoff = kind == "merge" or (kind == "source" and "mdm" in body)
            receipts = None
            if requires_handoff:
                if not selected["approved_by"]:
                    raise Blocked("MDM handoff requires approval of this Rules version")
                if mdm_engine is None:
                    raise Blocked("MDM activation requires an explicit destination connection")
                if kind == "source" and "acquisition" not in body:
                    raise Blocked("Source MDM activation requires approved acquisition authority")
                from edgar_warehouse.mdm.clean.store import register_policy, register_dataset, current_reading
                receipts = {"rules_digest": selected["digest"], "datasets": {}}
                # First commit the idempotent MDM handoff. If the Rules status
                # acknowledgement is lost, retry reconciles registered bodies.
                with mdm_engine.begin() as destination:
                    if kind == "merge":
                        receipts["policy_digest"] = register_policy(destination, body)
                    elif "acquisition" in body:
                        from edgar_warehouse.change_journal.authority import registration_authority
                        selected_export = self.envelope(selected)
                        for code, entry in body["mdm"].items():
                            registration_authority(selected_export, code, entry["contract"])
                            existing = destination.execute(text("SELECT mapping_version,body FROM mdm_v2.dataset_mapping WHERE source_code=:c ORDER BY mapping_version DESC LIMIT 1"), {"c": code}).mappings().first()
                            if existing is None or {k: v for k, v in existing["body"].items() if k != "registry_evidence"} != entry["contract"]:
                                register_dataset(destination, code, entry["contract"], rules_authority=selected_export)
                            reading = current_reading(destination, code)
                            receipts["datasets"][code] = {"mapping_version": reading[0], "digest": digest(reading[1])}
            conn.execute(text("UPDATE rules.rule_version SET status='retired' WHERE kind=:k AND name=:n AND status='active'"), {"k": kind, "n": name})
            conn.execute(text("UPDATE rules.rule_version SET status='active',clean_mdm=CAST(:receipt AS jsonb) WHERE kind=:k AND name=:n AND version=:v"), {"k": kind, "n": name, "v": version, "receipt": canonical(receipts)})

    def export(self, kind, name, version, *, root: str, artifacts: Artifacts | None = None) -> dict:
        row = self.version(kind, name, version)
        return (artifacts or Artifacts()).put(root, self.envelope(row))

    @staticmethod
    def envelope(row) -> dict:
        body = json.loads(row["body"])
        if digest(body) != row["digest"]:
            raise Blocked("Rules canonical content digest mismatch")
        approval = None
        if row["approved_by"]:
            approval = {"digest": row["digest"], "by": row["approved_by"], "at": row["approved_at"].isoformat()}
            # Approvals made on evidence carry their words and what they rest on.
            approval.update({key: row[column] for key, column in (
                ("words", "approved_words"), ("overrule", "approval_overrule"),
                ("evidence", "approval_evidence"), ("recorded_by", "approval_recorded_by")) if row.get(column)})
        return {"kind": row["kind"], "name": row["name"], "version": row["version"], "digest": row["digest"],
                "body": body, "status": row["status"], "proof": row["proof"], "approval": approval,
                "registration": row["clean_mdm"]}

    def resolve(self, kind, name, *, root: str, artifacts: Artifacts | None = None) -> dict:
        with self.engine.connect() as conn:
            selected = conn.execute(text("SELECT * FROM rules.rule_version WHERE kind=:k AND name=:n AND status='active'"), {"k": kind, "n": name}).mappings().first()
            if selected is None:
                raise Blocked("No active proven Rules version; authoring files cannot be executed")
            envelope = self.envelope(selected)
        return (artifacts or Artifacts()).put(root, envelope)

    def to_file(self, kind, name, version, path: Path):
        row = self.version(kind, name, version)
        # Digest-stable, not byte-stable: comments and YAML key order are
        # authoring metadata and are intentionally absent from canonical JSON.
        files.LAYOUT[kind][1](json.loads(row["body"]), path)

    def from_files(self, root: Path, version: str) -> list[dict]:
        """The same save lifecycle for every supported authoring document."""
        result = []
        for kind, folder, filename in (("source", "sources", "source.yaml"), ("pipeline", "pipelines", "pipeline.yaml")):
            for path in sorted((root / folder).glob(f"*/{filename}")):
                result.append(self.save(kind, path.parent.name, version, files.LAYOUT[kind][0](path)))
        if (root / "merge/policy.yaml").exists():
            result.append(self.save("merge", "platform", version, files.LAYOUT["merge"][0](root / "merge/policy.yaml")))
        return result

    def to_files(self, root: Path, version: str) -> list[dict]:
        with self.engine.connect() as conn:
            documents = [dict(row) for row in conn.execute(text("SELECT * FROM rules.rule_version WHERE version=:v ORDER BY kind,name"), {"v": version}).mappings()]
        if sum(row["kind"] == "merge" for row in documents) > 1:
            raise Blocked("The authoring layout has one platform policy; export named merge documents separately")
        for row in documents:
            if row["kind"] == "merge":
                path = root / "merge" / "policy.yaml"
            else:
                folder, filename = ("sources", "source.yaml") if row["kind"] == "source" else ("pipelines", "pipeline.yaml")
                path = root / folder / row["name"] / filename
            self.to_file(row["kind"], row["name"], version, path)
        return [{"kind": row["kind"], "name": row["name"], "digest": row["digest"]} for row in documents]


def changes(before: dict | None, after: dict, path: str = "") -> list[str]:
    """What a version changes from another, one line per changed value, by
    its place in the document; the skill turns them into plain words."""
    if before is None and not path:
        return ["new: nothing of this name is active yet"]
    if isinstance(before, dict) and isinstance(after, dict):
        found = []
        for key in sorted(set(before) | set(after)):
            where = f"{path}.{key}" if path else key
            if key not in before:
                found.append(f"added {where}")
            elif key not in after:
                found.append(f"removed {where}")
            else:
                found.extend(changes(before[key], after[key], where))
        return found
    if before == after:
        return []
    if isinstance(before, list) and isinstance(after, list):
        # Rules in a list are named by their rule_id: say which came or went.
        def named(items):
            return {i["rule_id"]: i for i in items if isinstance(i, dict) and "rule_id" in i}
        old, new = named(before), named(after)
        if len(old) == len(before) and len(new) == len(after):
            return ([f"added {path}: {key}" for key in new if key not in old]
                    + [f"removed {path}: {key}" for key in old if key not in new]
                    + [line for key in new if key in old for line in changes(old[key], new[key], f"{path}[{key}]")])
    shown = [json.dumps(value, default=str) for value in (before, after)]
    return [f"changed {path}: " + " -> ".join(v if len(v) <= 120 else v[:117] + "..." for v in shown)]
