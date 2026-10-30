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

from datetime import UTC, datetime

from sqlalchemy import create_engine, select, text, update

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.bookkeeping.clean.config import Blocked, canonical, digest
from . import files, storage


# A version waits for approval once a test run is recorded and until approved.
WAITING = "proof IS NOT NULL AND approved_by IS NULL AND status IN ('draft','proven')"
# The evidence an approval rests on; the trigger stores the same expression.
EVIDENCE_HASH = "encode(sha256(convert_to(proof::text,'UTF8')),'hex')"
APPROVAL_COLUMNS = "approved_by,approved_at,approved_words,approval_overrule,approval_evidence,approval_recorded_by"


def get_engine(url=None):
    return create_engine(url or os.environ["RULES_DATABASE_URL"], pool_pre_ping=True, hide_parameters=True)


def migrate(engine, *, agent_role: str = "rules_agent", approver_role: str = "rules_approver", database_name: str = "rules"):
    if engine.dialect.name == "mysql":
        from .mysql import migrate as selected_migrate
        return selected_migrate(engine, agent_role=agent_role, approver_role=approver_role, database_name=database_name)
    if engine.dialect.name != "postgresql":
        raise Blocked("Rules currently supports PostgreSQL and MySQL; SQL Server follows last")
    paths = sorted((Path(__file__).parent / "migrations").glob("[0-9]*.sql"))
    base_checksum = hashlib.sha256(paths[0].read_bytes()).hexdigest()
    quote = engine.dialect.identifier_preparer.quote
    with engine.begin() as conn:
        if conn.scalar(text("SELECT current_database()")) != database_name or int(conn.scalar(text("SHOW server_version_num"))) // 10000 != 16:
            raise Blocked("Rules migration requires its own rules database on PostgreSQL 16")
        role = conn.execute(text("SELECT rolsuper,rolcreatedb,rolcreaterole FROM pg_roles WHERE rolname=:r"), {"r": agent_role}).first()
        if not role or any(role) or conn.scalar(text("SELECT current_user")) == agent_role:
            raise Blocked("Restricted Rules agent and separate migration owner required")
        if not conn.scalar(text("SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=:r)"), {"r": approver_role}):
            raise Blocked("Create the configured approval role explicitly")
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
        agent, approver = quote(agent_role), quote(approver_role)
        conn.exec_driver_sql(f"REVOKE ALL ON ALL TABLES IN SCHEMA rules FROM PUBLIC,{agent},{approver}")
        conn.exec_driver_sql(f"GRANT USAGE ON SCHEMA rules TO {agent},{approver}")
        conn.exec_driver_sql(f"GRANT SELECT ON rules.rule_version TO {agent},{approver}")
        conn.exec_driver_sql(f"GRANT INSERT(kind,name,version,body,digest) ON rules.rule_version TO {agent}")
        conn.exec_driver_sql(f"GRANT UPDATE(status,proof,batch_hash,clean_mdm) ON rules.rule_version TO {agent}")
        # The agent records the operator's approval in their name and words
        # (operator, 2026-09-29, rules skill ticket 14); the trigger refuses
        # one without test evidence or without those words.
        conn.exec_driver_sql(f"GRANT UPDATE({APPROVAL_COLUMNS}) ON rules.rule_version TO {agent},{approver}")
        if conn.scalar(text("SELECT has_schema_privilege(:r,'rules','CREATE')"), {"r": agent_role}):
            raise Blocked("Rules agent owns the Rules schema")
    return checksums


class Rules:
    def __init__(self, engine):
        self.engine = engine

    def save(self, kind: str, name: str, version: str, body: dict) -> dict:
        if (kind not in ("source", "merge", "pipeline") or not isinstance(name, str) or not isinstance(version, str)
                or not re.fullmatch(r"[a-z][a-z0-9_.-]*", name) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", version)):
            raise Blocked("A supported document kind, name and version are required")
        files.check_document(kind, body)
        table = storage.versions(self.engine.dialect.name)
        with storage.transaction(self.engine, kind, name) as conn:
            storage.save(conn, table, {"kind": kind, "name": name, "version": version,
                                       "body": canonical(body), "digest": digest(body)})
            row = self._version(conn, kind, name, version)
            if row["digest"] != digest(body) or row["body"] != canonical(body):
                raise Blocked("The version label already names different immutable content")
        return row

    @staticmethod
    def _version(conn, kind, name, version):
        row = storage.version(conn, kind, name, version)
        if row is None:
            raise Blocked("Unknown Rules version")
        return dict(row)

    def version(self, kind, name, version):
        with self.engine.connect() as conn:
            return self._version(conn, kind, name, version)

    def history(self, kind, name):
        table = storage.versions(self.engine.dialect.name)
        columns = ("kind", "name", "version", "digest", "status", "proved_at", "approved_by", "approved_at",
                   "approved_words", "approval_overrule")
        with self.engine.connect() as conn:
            return storage.rows(conn, select(*(table.c[column] for column in columns)).where(
                storage.identity(table, conn.dialect.name, kind, name)).order_by(table.c.created_at))

    def prove(self, kind, name, version, proof):
        """Record a test run of this version, passing or not. A passing one
        makes it proven; a failing one stays a draft with its evidence, which
        the operator may overrule on approval (and a new run may replace). A
        source's acquisition evidence, when the proof carries it, is checked
        when the run passed, and an overrule never covers acquisition evidence
        of a source that could not be read (the trigger refuses it at
        proven). A test run over captured data carries none: it proves the
        pipes over what was captured, not live acquisition (operator,
        2026-10-19)."""
        if type(proof.get("passed")) is not bool:
            raise Blocked("A proof says whether it passed")
        row = self.version(kind, name, version)
        body = json.loads(row["body"])
        if "acquisition" in body and "acquisition" in proof and proof["passed"]:
            from edgar_warehouse.rules.acquisition_authority import validation_proof
            validation_proof(body, proof, artifacts=Artifacts())
        table = storage.versions(self.engine.dialect.name)
        with storage.transaction(self.engine, kind, name) as conn:
            conn.execute(update(table).where(storage.identity(table, conn.dialect.name, kind, name, version)).values(
                status="proven" if proof["passed"] else "draft", proof=proof, batch_hash=proof["batch_hash"]))

    def pending(self) -> list[dict]:
        """Every version with a recorded test run and no approval yet, with its
        evidence, the hash an approval of it must name, and what it changes
        from the active version."""
        table = storage.versions(self.engine.dialect.name)
        with self.engine.connect() as conn:
            waiting = storage.rows(conn, select(table, storage.evidence(table, conn.dialect.name).label("evidence_hash")).where(
                table.c.proof.is_not(None), table.c.approved_by.is_(None), table.c.status.in_(["draft", "proven"])).order_by(
                table.c.kind, table.c.name, table.c.proved_at.desc()))
            active = {(r["kind"], r["name"]): json.loads(r["body"]) for r in storage.rows(conn,
                select(table.c.kind, table.c.name, table.c.body).where(table.c.status == "active"))}
        return [{"kind": r["kind"], "name": r["name"], "version": r["version"], "passed": r["proof"]["passed"],
                 "evidence": r["proof"].get("evidence"), "note": r["proof"].get("note"), "proved_at": r["proved_at"],
                 "evidence_hash": r["evidence_hash"],
                 "changes": version_changes(active.get((r["kind"], r["name"])), json.loads(r["body"]))} for r in waiting]

    def approve(self, kind, name, version, *, evidence: str, by: str, words: str, overrule: str | None = None) -> dict:
        """Record the operator's approval, in their name and exact words, of the
        version and test run they were shown (`evidence`, the hash `pending`
        gave). A version or run recorded since is not what they read, so it is
        refused. No approval without test evidence; a failing run only with an
        overrule reason."""
        table = storage.versions(self.engine.dialect.name)
        with storage.transaction(self.engine, kind, name) as conn:
            found = storage.rows(conn, select(table, storage.evidence(table, conn.dialect.name).label("evidence_hash")).where(
                storage.identity(table, conn.dialect.name, kind, name, version)).with_for_update())
            row = found[0] if found else None
            if row is None:
                raise Blocked("Unknown Rules version")
            if row["proof"] is None:
                raise Blocked("No approval without test evidence: record a test run first")
            if row["evidence_hash"] != evidence:
                raise Blocked("The test run differs from the one shown for approval: show it again first")
            if row["proof"]["passed"] is False and not (overrule or "").strip():
                raise Blocked("The test run failed: approving it needs an overrule reason")
            # Only an overruled failing run changes the status: it is what
            # makes that version proven. A passing one is proven already.
            values = {"approved_by": by, "approved_words": words, "approval_overrule": overrule or None,
                      "approved_at": datetime.now(UTC)}
            if row["status"] == "draft": values["status"] = "proven"
            conn.execute(update(table).where(storage.identity(table, conn.dialect.name, kind, name, version)).values(**values))
            return self._version(conn, kind, name, version)

    def activate(self, kind, name, version, *, mdm_engine=None):
        table = storage.versions(self.engine.dialect.name)
        with storage.transaction(self.engine, kind, name) as conn:
            selected = self._version(conn, kind, name, version)
            if selected["status"] == "active":
                return
            if selected["status"] != "proven":
                raise Blocked("Only a proven version can activate")
            body = json.loads(selected["body"])
            if "acquisition" in body and "acquisition" in selected["proof"]:
                from edgar_warehouse.rules.acquisition_authority import validation_proof
                validation_proof(body, selected["proof"], artifacts=Artifacts())
            requires_handoff = kind == "merge" or (kind == "source" and "mdm" in body)
            receipts = None
            if requires_handoff:
                if not selected["approved_by"]:
                    raise Blocked("MDM handoff requires approval of this Rules version")
                if mdm_engine is None:
                    raise Blocked("MDM activation requires an explicit destination connection")
                from edgar_warehouse.mdm.clean.store import register_policy, register_dataset, current_reading
                receipts = {"rules_digest": selected["digest"], "datasets": {}}
                # First commit the idempotent MDM handoff. If the Rules status
                # acknowledgement is lost, retry reconciles registered bodies.
                with mdm_engine.begin() as destination:
                    if kind == "merge":
                        receipts["policy_digest"] = register_policy(destination, body)
                    else:
                        from edgar_warehouse.rules.acquisition_authority import registration_authority
                        selected_export = self.envelope(selected)
                        for code, entry in body["mdm"].items():
                            registration_authority(selected_export, code, entry["contract"])
                            existing_reading = current_reading(destination, code)
                            existing = existing_reading[1] if existing_reading is not None else None
                            # A dataset belongs to the source that first registered it.
                            owner = (((existing or {}).get("registry_evidence") or {}).get("rules") or {}).get("name")
                            if owner is not None and owner != name:
                                raise Blocked(f"Dataset {code} belongs to source {owner}, not {name}")
                            if existing is None or {k: v for k, v in existing.items() if k != "registry_evidence"} != entry["contract"]:
                                register_dataset(destination, code, entry["contract"], rules_authority=selected_export)
                            reading = current_reading(destination, code)
                            receipts["datasets"][code] = {"mapping_version": reading[0], "digest": digest(reading[1])}
            conn.execute(update(table).where(storage.identity(table, conn.dialect.name, kind, name, active=True)).values(status="retired"))
            conn.execute(update(table).where(storage.identity(table, conn.dialect.name, kind, name, version)).values(
                status="active", clean_mdm=receipts))

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
        table = storage.versions(self.engine.dialect.name)
        with self.engine.connect() as conn:
            found = storage.rows(conn, select(table).where(storage.identity(table, conn.dialect.name, kind, name, active=True)))
            selected = found[0] if found else None
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
        return [self.save(kind, name, version, files.LAYOUT[kind][0](path)) for kind, name, path in files.documents(root)]

    def to_files(self, root: Path, version: str) -> list[dict]:
        table = storage.versions(self.engine.dialect.name)
        with self.engine.connect() as conn:
            documents = storage.rows(conn, select(table).where(table.c.version == version).order_by(table.c.kind, table.c.name))
        if sum(row["kind"] == "merge" for row in documents) > 1:
            raise Blocked("The authoring layout has one platform policy; export named merge documents separately")
        for row in documents:
            if row["kind"] == "merge":
                path = root / "merge" / "policy.yaml"
            else:
                folder, filename = ("sources", "source.yaml") if row["kind"] == "source" else ("pipelines", "pipeline.yaml")
                path = root / folder / row["name"] / filename
            self.to_file(row["kind"], row["name"], version, path)
        files.copy_identifiers(root)
        return [{"kind": row["kind"], "name": row["name"], "digest": row["digest"]} for row in documents]


def version_changes(before: dict | None, after: dict, path: str = "") -> list[str]:
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
                found.extend(version_changes(before[key], after[key], where))
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
                    + [line for key in new if key in old for line in version_changes(old[key], new[key], f"{path}[{key}]")])
    shown = [json.dumps(value, default=str) for value in (before, after)]
    return [f"changed {path}: " + " -> ".join(v if len(v) <= 120 else v[:117] + "..." for v in shown)]
