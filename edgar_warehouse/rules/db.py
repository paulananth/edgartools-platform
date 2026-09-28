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
        conn.exec_driver_sql("GRANT UPDATE(approved_by,approved_at) ON rules.rule_version TO rules_approver")
        if conn.scalar(text("SELECT has_schema_privilege(:r,'rules','CREATE') OR has_column_privilege(:r,'rules.rule_version','approved_by','INSERT,UPDATE') OR has_column_privilege(:r,'rules.rule_version','approved_at','INSERT,UPDATE')"), {"r": agent_role}):
            raise Blocked("Rules agent inherits approval privileges or schema ownership")
    return checksums


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
        row = self.version(kind, name, version)
        body = json.loads(row["body"])
        if "acquisition" in body:
            from edgar_warehouse.change_journal.authority import validation_proof
            validation_proof(body, proof, artifacts=Artifacts())
        with self.engine.begin() as conn:
            conn.execute(text("UPDATE rules.rule_version SET status='proven',proof=CAST(:p AS jsonb),batch_hash=:h WHERE kind=:k AND name=:n AND version=:v"),
                         {"p": canonical(proof), "h": proof["batch_hash"], "k": kind, "n": name, "v": version})

    def approve(self, kind, name, version, expected_digest):
        with self.engine.begin() as conn:
            row = self._version(conn, kind, name, version)
            if row["digest"] != expected_digest:
                raise Blocked("Approval digest differs from the selected version")
            conn.execute(text("UPDATE rules.rule_version SET approved_by=session_user,approved_at=clock_timestamp() WHERE kind=:k AND name=:n AND version=:v"), {"k": kind, "n": name, "v": version})

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
