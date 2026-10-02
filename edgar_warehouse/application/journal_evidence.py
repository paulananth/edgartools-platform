"""Producer workflow evidence; planning never opens a database connection."""

from __future__ import annotations

import json
import os
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.bookkeeping.clean.capabilities import standard_registry
from edgar_warehouse.bookkeeping.clean.config import (
    Blocked,
    canonical,
    digest,
    validate,
    worklist,
)
from edgar_warehouse.bookkeeping.clean.feeds import resolve_feed
from edgar_warehouse.bookkeeping.clean.mdm_capabilities import register_mdm
from edgar_warehouse.rules.files import load

from edgar_warehouse.acquisition.capture import register_capture
from edgar_warehouse.application.source_evidence import register_source_evidence


def verify_validation(bundle, evidence, *, book_engine, journal_engine, artifacts):
    """Read committed validation authority; a JSON report is not an attestation.

    For a different deployment store, provide both explicit read connections
    to the retained validation stores. Never infer an old ledger connection.
    This function performs no control or provider mutations.
    """
    from edgar_warehouse.change_journal.store import ChangeJournal

    urls = (
        os.environ.get("BOOKKEEPING_VALIDATION_DATABASE_URL"),
        os.environ.get("CHANGE_JOURNAL_VALIDATION_DATABASE_URL"),
    )
    if bool(urls[0]) != bool(urls[1]):
        raise Blocked("Supply both retained validation store connections")
    owned = (
        [create_engine(url, pool_pre_ping=True) for url in urls] if all(urls) else []
    )
    control, journal = owned or [book_engine, journal_engine]
    try:
        with control.connect() as conn, conn.begin():
            conn.execute(text("SET TRANSACTION READ ONLY"))
            if (
                int(conn.scalar(text("SHOW server_version_num"))) // 10000 != 16
                or conn.scalar(text("SELECT current_database()")) != "bookkeeping_clean"
            ):
                raise Blocked(
                    "Validation authority requires the fresh PostgreSQL 16 Bookkeeping store"
                )
            row = (
                conn.execute(
                    text(
                        "SELECT * FROM bookkeeping.pipeline_run WHERE run_id=CAST(:r AS uuid)"
                    ),
                    {"r": evidence["run_id"]},
                )
                .mappings()
                .one_or_none()
            )
            if row is None or row["state"] != "complete":
                raise Blocked("Validation root is missing or has not completed")
            submission = row["submission"]
            if (
                digest(submission) != row["submission_hash"]
                or submission.get("journal") != "change-journal-v1"
                or submission["inputs"] != bundle["inputs"]
                or submission["processing_versions"] != bundle["processing_versions"]
                or submission["name"] != bundle["source"]
                or submission["scope"].get("feed") != bundle["feed"]
                or submission["target"] != bundle["target"]
                or artifacts.json(submission["rules"])["digest"]
                != bundle["rules_digest"]
                or row["checks"] != evidence["checks"]
                or not row["checks"]
                or any(value is not True for value in row["checks"].values())
            ):
                raise Blocked(
                    "Committed validation scope or checks differ from the retained plan"
                )
            rows = (
                conn.execute(
                    text(
                        "SELECT step,state,count(*) AS count FROM bookkeeping.work_item WHERE run_id=CAST(:r AS uuid) GROUP BY step,state"
                    ),
                    {"r": evidence["run_id"]},
                )
                .mappings()
                .all()
            )
            counts = {step: 0 for step in bundle["expected"]}
            for work in rows:
                if work["state"] != "verified" or work["step"] not in counts:
                    raise Blocked("Validation includes unverified or undeclared work")
                counts[work["step"]] = work["count"]
            pending = conn.scalar(
                text(
                    "SELECT count(*) FROM bookkeeping.journal_outbox WHERE run_id=CAST(:r AS uuid) AND delivered_at IS NULL"
                ),
                {"r": evidence["run_id"]},
            )
            if (
                counts != bundle["expected"]
                or pending
                or row["expected_count"] != sum(counts.values())
            ):
                raise Blocked("Validation accounting or delivery backlog differs")
        with journal.connect() as conn:
            if (
                int(conn.scalar(text("SHOW server_version_num"))) // 10000 != 16
                or conn.scalar(text("SELECT current_database()"))
                != "change_journal_clean"
            ):
                raise Blocked(
                    "Validation receipts require the fresh PostgreSQL 16 journal"
                )
        sink = ChangeJournal(journal)
        actual = sink.list(
            source=bundle["source"],
            feed=bundle["feed"],
            run_id=evidence["run_id"],
            limit=1000,
        )
        if not actual or actual != evidence["receipts"]:
            raise Blocked(
                "Validation receipt inspection differs from durable read-back"
            )
        for receipt in actual:
            sink.verify(receipt)
    finally:
        for engine in owned:
            engine.dispose()


def plan(
    *, source: str, feed: str, target: str, inputs: dict, rules_root: Path
) -> dict:
    binding = resolve_feed(rules_root, source, feed)
    feed = binding["feed"]
    document = load(rules_root / "sources" / binding["source"] / "source.yaml")
    registry = standard_registry()
    register_capture(registry, None)
    register_source_evidence(registry)

    def planning_publisher(_):
        raise Blocked("Planning never opens a publication destination")

    register_mdm(registry, None, publisher_factory=planning_publisher)
    configuration = validate(document, target, registry)
    manifest = Artifacts().json(inputs)
    items = worklist(manifest, configuration)
    for item in items:
        unit = item["unit"]
        if "from" in unit["input"]:
            continue  # Exact prerequisite selectors are already validated.
        data = Artifacts().json(unit["input"])
        declared = (data.get("source"), data.get("feed"))
        keys = (unit["keys"].get("source"), unit["keys"].get("feed"))
        if declared != (binding["source"], feed) and keys != (binding["source"], feed):
            raise Blocked("Plan input lacks explicit selected source/feed membership")
        if "source_input" in data:
            Artifacts().verified(
                data["source_input"]["artifact"], max_bytes=16 * 1024**2
            )
    value = {
        "version": 1,
        "source": binding["source"],
        "feed": feed,
        "binding": binding,
        "target": target,
        "rules_digest": digest(document),
        "inputs": inputs,
        "processing_versions": {
            s["operation"]: registry.operations[s["operation"]].version
            for s in configuration["steps"]
        },
        "expected": {
            s["name"]: sum(i["step"] == s["name"] for i in items)
            for s in configuration["steps"]
        },
    }
    return {**value, "plan_hash": digest(value)}


def execute(
    mode: str,
    bundle: dict,
    *,
    source: str,
    feed: str,
    evidence: dict | None = None,
    limit: int = 100,
) -> dict:
    if (
        mode not in {"validate", "deploy"}
        or source not in {bundle["source"], bundle["binding"]["requested_source"]}
        or feed
        not in {bundle["feed"], bundle["binding"].get("requested_feed", bundle["feed"])}
    ):
        raise Blocked("Mode and source/feed must match the planned scope")
    source, feed = bundle["source"], bundle["feed"]
    if bundle["plan_hash"] != digest(
        {k: v for k, v in bundle.items() if k != "plan_hash"}
    ):
        raise Blocked("Plan bundle hash differs")
    if mode == "validate":
        if os.environ.get("MDM_DATABASE_URL"):
            url = make_url(os.environ["MDM_DATABASE_URL"])
            if url.host not in {"127.0.0.1", "localhost", "::1"} or not (
                url.database or ""
            ).startswith("change_journal_validation_"):
                raise Blocked(
                    "MDM validation requires an isolated change_journal_validation_* local database"
                )
        for variable, database in (
            ("BOOKKEEPING_CLEAN_DATABASE_URL", "bookkeeping_clean"),
            ("CHANGE_JOURNAL_DATABASE_URL", "change_journal_clean"),
            ("RULES_DATABASE_URL", "rules"),
        ):
            url = make_url(os.environ[variable])
            if (
                url.host not in {"127.0.0.1", "localhost", "::1"}
                or url.database != database
            ):
                raise Blocked(
                    "Validation requires explicit isolated local PostgreSQL 16 stores"
                )
    if mode == "deploy" and (
        not evidence
        or evidence.get("mode") != "validate"
        or evidence.get("qualified") is not True
        or evidence.get("plan_hash") != bundle["plan_hash"]
        or (evidence.get("source"), evidence.get("feed")) != (source, feed)
        or evidence.get("processing_versions") != bundle["processing_versions"]
        or evidence.get("expected") != bundle["expected"]
        or evidence.get("verified") != bundle["expected"]
        or evidence.get("pending_deliveries") != 0
        or not evidence.get("checks")
        or any(v is not True for v in evidence["checks"].values())
        or not evidence.get("receipts")
    ):
        raise Blocked(
            "Deployment requires matching complete source/feed validation evidence"
        )
    from edgar_warehouse.bookkeeping.clean.cli import configured_bookkeeping
    from edgar_warehouse.bookkeeping.clean.runner import run
    from edgar_warehouse.rules.db import Rules
    from edgar_warehouse.rules.db import get_engine as rules_engine

    from edgar_warehouse.change_journal.store import ChangeJournal
    from edgar_warehouse.change_journal.store import get_engine as journal_engine

    book = configured_bookkeeping()
    rules, journal = rules_engine(), journal_engine()
    try:
        if mode == "deploy":
            verify_validation(
                bundle,
                evidence,
                book_engine=book.engine,
                journal_engine=journal,
                artifacts=book.artifacts,
            )
        if mode == "validate":
            for engine in (book.engine, rules, journal):
                with engine.connect() as conn:
                    if int(conn.scalar(text("SHOW server_version_num"))) // 10000 != 16:
                        raise Blocked("Validation requires PostgreSQL 16")
        ref = Rules(rules).resolve(
            "source",
            source,
            root=os.environ["BOOKKEEPING_MANIFEST_ROOT"],
            artifacts=book.artifacts,
        )
        export = book.artifacts.json(ref)
        if export["digest"] != bundle["rules_digest"]:
            raise Blocked("Active Rules configuration differs from the plan")
        approval = export.get("approval") or {}
        if approval.get("digest") != export["digest"] or not approval.get("by"):
            raise Blocked(
                "Skill execution requires approval of the exact configuration"
            )
        configuration = validate(export["body"], bundle["target"], book.registry)
        versions = {
            s["operation"]: book.registry.operations[s["operation"]].version
            for s in configuration["steps"]
        }
        if versions != bundle["processing_versions"]:
            raise Blocked("Processing versions differ from validation")
        book.artifacts.verified(bundle["inputs"])
        rid = None
        if mode == "deploy":
            with book.engine.connect() as conn:
                found = conn.scalar(
                    text(
                        "SELECT EXISTS(SELECT 1 FROM bookkeeping.pipeline_run WHERE run_id=CAST(:r AS uuid))"
                    ),
                    {"r": evidence["run_id"]},
                )
            if found:
                original = book._run(evidence["run_id"])["submission"]
                if (
                    original["inputs"] != bundle["inputs"]
                    or original["processing_versions"] != versions
                    or original["name"] != source
                    or original["scope"].get("feed") != feed
                    or original["target"] != bundle["target"]
                    or book.artifacts.json(original["rules"])["digest"]
                    != bundle["rules_digest"]
                ):
                    raise Blocked(
                        "Retained validation root differs from deployment scope"
                    )
                book.resume(evidence["run_id"])
                rid = evidence["run_id"]
        if rid is None:
            rid = book.start(
                rules_ref=ref,
                inputs_ref=bundle["inputs"],
                target=bundle["target"],
                scope={"source": source, "feed": feed},
            )
        sink = ChangeJournal(journal)
        result = run(book, rid, sink, limit=limit)
        # Counts cover all work, even when the operator status listing is bounded.
        with book.engine.connect() as conn:
            actual = {
                row.step: row.count
                for row in conn.execute(
                    text(
                        "SELECT step,count(*) FROM bookkeeping.work_item WHERE run_id=CAST(:r AS uuid) AND state='verified' GROUP BY step"
                    ),
                    {"r": rid},
                )
            }
            verified = {step: actual.get(step, 0) for step in bundle["expected"]}
        receipts = sink.list(source=source, feed=feed, run_id=rid, limit=1000)
        for receipt in receipts:
            sink.verify(receipt)
        return {
            "version": 1,
            "mode": mode,
            "source": source,
            "feed": feed,
            "plan_hash": bundle["plan_hash"],
            "rules_digest": export["digest"],
            "inputs": bundle["inputs"],
            "processing_versions": versions,
            "run_id": rid,
            "expected": bundle["expected"],
            "verified": verified,
            "checks": result["run"]["checks"],
            "pending_deliveries": result["pending_deliveries"],
            "receipts": receipts,
            "qualified": result["run"]["state"] == "complete"
            and verified == bundle["expected"],
        }
    finally:
        book.close()
        rules.dispose()
        journal.dispose()


def main():
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("plan", "validate", "deploy"))
    parser.add_argument("--source", required=True)
    parser.add_argument("--feed", required=True)
    parser.add_argument(
        "--rules-root", type=Path, default=Path(__file__).resolve().parents[2] / "rules"
    )
    parser.add_argument("--target")
    parser.add_argument("--input-manifest")
    parser.add_argument("--input-sha256")
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--validation", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    if args.mode == "plan":
        if not args.target or not args.input_manifest or not args.input_sha256:
            parser.error("plan requires target and exact input manifest URI/hash")
        value = plan(
            source=args.source,
            feed=args.feed,
            target=args.target,
            inputs={"uri": args.input_manifest, "sha256": args.input_sha256},
            rules_root=args.rules_root,
        )
    else:
        if not args.plan:
            parser.error("execution requires a retained plan")
        bundle = json.loads(args.plan.read_text())
        evidence = json.loads(args.validation.read_text()) if args.validation else None
        value = execute(
            args.mode,
            bundle,
            source=args.source,
            feed=args.feed,
            evidence=evidence,
            limit=args.limit,
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(canonical(value) + "\n")
    print(json.dumps(value, indent=2, sort_keys=True))
    return 3 if args.mode != "plan" and not value["qualified"] else 0
