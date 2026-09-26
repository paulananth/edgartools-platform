"""Ticket 05, Phase 1: the Proving Run of the CIK matching rule.

Every SEC Company in CIK manifest v1 (`05-manifest.json`), plus 586
controls, through the unchanged production path: the seven bundles
`prepare-clean-company` built from seven `bootstrap-batch` captures of real
bronze, applied by the Merge Stage (`execute_manifest`) on a disposable
PostgreSQL 16 under the restricted runtime role (the Clean MDM test
fixtures). The container is removed afterwards; nothing shared is touched.

The candidate policy is the approved Company policy (`983352e8…4049`) plus
the CIK matching rule, its Identifier Contract and a deterministic
activation. Activation requires the contract's verification to name an
approval, so the run registers a copy stamped as a Proving Run; the body the
operator is asked to approve (ticket 06) differs only in those three fields,
which this report shows.

Each bundle is applied as prepared, except that its manifest names the
candidate policy's digest instead of the live policy's. Then all seven are
applied again under a new run; the second pass must create nothing.

    PROVING_BUNDLES=<dir holding chunk1..chunk7> PROVING_OUT=<report.json> \\
    PROVING_MANIFEST_SHA256=<sha256 of 05-manifest.json> \\
    [PROVING_CHUNKS=1,2,...  (default all seven; a trial runs fewer)] \\
    DOCKER_HOST=unix://$HOME/.colima/default/docker.sock \\
    uv run --no-sync pytest -q -p no:cacheprovider -s \\
        .scratch/company-mastering/research/05_proving_run.py
"""

from __future__ import annotations

import copy
import json
import os
import shutil
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from sqlalchemy import text

from edgar_warehouse.mdm.clean.bookkeeping import RunCoordinator
from edgar_warehouse.mdm.clean.cli import execute_manifest
from edgar_warehouse.mdm.clean.company_source import (
    CONTRACT,
    POLICY,
    SOURCE_CODE,
)
from edgar_warehouse.mdm.clean.store import (
    Store,
    canonical,
    digest,
    register_dataset,
    register_policy,
)
from tests.integration import test_clean_mdm_postgres as core

postgres = core.postgres
database = core.database
command_databases = core.command_databases

LIVE_POLICY = "983352e81d295a165a1391e82fa8a24a710e6f638361a577f18f541917fd4049"
VERSION = "company-2026-09-26.cik-matching-rule"

# The CIK matching rule (ticket 04): an SEC record the Company rule accepts
# joins the one Company its CIK is on, and creates one when none is.
CIK_RULE = {
    "rule_id": "company-cik",
    "version": "2026-09-24",
    "family": "binding",
    "applies_to_verdict": "company",
    "emits": ["bind"],
    "on_no_match": "mint",
    "source": SOURCE_CODE,
    "when": [
        {"primitive": "identifier_match@1", "args": {"namespace": "cik"}},
        {"primitive": "identifier_cardinality@1", "args": {"namespace": "cik"}},
    ],
}


def cik_contract(corpus_sha256: str, approval: dict) -> dict:
    """The CIK Identifier Contract (policy-language.md §9.3; Company Q14).

    Tolerance is the spec's declared line for an SEC CIK contract.
    """
    return {
        "authority": "SEC/EDGAR",
        "sources": [SOURCE_CODE],
        "normalizer": "normalize_identifier@sec-cik-v1",
        "claim": {"forward": 1, "reverse": None},
        "compatibility": {"field": "kind", "predicate": "kind_equal@1"},
        "verification": {"corpus_sha256": corpus_sha256, **approval},
        "tolerance": {"unit": "items", "warm_up_decisions": 10000, "max_per_10k": 5},
    }


def candidate(corpus_sha256: str, approval: dict) -> dict:
    body = copy.deepcopy(POLICY)
    body["version"] = VERSION
    block = body["kinds"]["company"]
    block["rules"] = [*block["rules"], CIK_RULE]
    block["identifiers"] = {"cik": cik_contract(corpus_sha256, approval)}
    body["automatic_rules"] = [
        *body["automatic_rules"],
        {
            "kind": "company",
            "family": "binding",
            "rule_id": CIK_RULE["rule_id"],
            "rule_version": CIK_RULE["version"],
            "verdict": "bind",
            "activation": "deterministic",
        },
    ]
    return body


PENDING = {"approved_by": None, "approved_at": None, "reason": None}


def counts(conn) -> dict:
    one = lambda sql: conn.execute(text(sql)).scalar()
    return {
        "identities": dict(
            conn.execute(
                text("SELECT kind, count(*) FROM mdm_v2.identity GROUP BY kind")
            ).all()
        ),
        "company_versions_open": one(
            "SELECT count(*) FROM mdm_v2.company WHERE valid_to IS NULL"
        ),
        "stage_records": dict(
            conn.execute(
                text(
                    "SELECT kind, count(*) FROM mdm_v2.stage_record "
                    "WHERE source_code=:s GROUP BY kind"
                ),
                {"s": SOURCE_CODE},
            ).all()
        ),
        "stage_bound": one(
            "SELECT count(*) FROM mdm_v2.stage_record WHERE entity_id IS NOT NULL"
        ),
        "waiting": one("SELECT count(*) FROM mdm_v2.stage_waiting"),
        "open_reviews": dict(
            conn.execute(
                text(
                    "SELECT coalesce(body->>'reason','(none)'), count(*) "
                    "FROM mdm_v2.projection WHERE object_type='review' "
                    "AND body->'open'='true'::jsonb GROUP BY 1"
                )
            ).all()
        ),
        "decisions": dict(
            conn.execute(
                text("SELECT operation, count(*) FROM mdm_v2.decision GROUP BY 1")
            ).all()
        ),
        "assessments": dict(
            conn.execute(
                text(
                    "SELECT body->>'outcome', count(*) FROM mdm_v2.assessment GROUP BY 1"
                )
            ).all()
        ),
        "batches": one("SELECT count(*) FROM mdm_v2.batch"),
    }


def records(conn) -> dict[str, dict]:
    """Each SEC record's outcome, by CIK."""
    out: dict[str, dict] = {}
    for key, kind, entity in conn.execute(
        text(
            "SELECT record_key, kind, entity_id::text FROM mdm_v2.stage_record "
            "WHERE source_code=:s"
        ),
        {"s": SOURCE_CODE},
    ):
        out[key] = {"stage_kind": kind, "entity_id": entity}
    for row in conn.execute(
        text(
            "SELECT raw_record->>'cik', probable_kind, reason, rule_step, blocking "
            "FROM mdm_v2.stage_waiting WHERE source_code=:s"
        ),
        {"s": SOURCE_CODE},
    ):
        cik = str(row[0]).zfill(10)
        out.setdefault(cik, {}).update(
            {
                "waiting": True,
                "probable_kind": row[1],
                "reason": row[2],
                "step": row[3],
                "blocking": row[4],
            }
        )
    return out


def test_proving_run(database, command_databases, tmp_path):
    bundles = Path(os.environ["PROVING_BUNDLES"])
    out = Path(os.environ["PROVING_OUT"])
    corpus = os.environ["PROVING_MANIFEST_SHA256"]
    assert digest(POLICY) == LIVE_POLICY, "the approved Company policy changed"

    proving = {
        "approved_by": "proving-run",
        "approved_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "reason": "Company mastering ticket 05 Proving Run only; not an approval",
    }
    pending_body = candidate(corpus, PENDING)
    proving_body = candidate(corpus, proving)

    # The disposable registry covers SEC submissions, as the shared one must
    # before any SEC Company batch registers there.
    with database.admin.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO source_registry_coverage(version_id,source_family,coverage_action,"
                "acquisition_mode,completeness_policy,discovery_policy,coverage_start_date) "
                "VALUES(:v,:f,'carry_forward','bronze','bounded_sample','manifest','2026-01-01')"
            ),
            {"v": database.registry, "f": CONTRACT["family"]},
        )
        register_dataset(conn, SOURCE_CODE, database.registry, CONTRACT)
        policy = register_policy(conn, proving_body)

    # Per-function timing, so the report says where Merge Stage time goes.
    with database.admin.connect().execution_options(
        isolation_level="AUTOCOMMIT"
    ) as conn:
        conn.execute(text("ALTER SYSTEM SET track_functions = 'pl'"))
        conn.execute(text("SELECT pg_reload_conf()"))
        conn.execute(text("SELECT pg_stat_reset()"))

    store = Store(database.application)
    coordinator = RunCoordinator(command_databases[0], store)

    # Each bundle is applied as soon as it exists (a bundle directory appears
    # whole, by rename), in the order given; the chunks share no CIK, so the
    # order changes no outcome. Each manifest gets its own run, as each
    # `mdm mastering --manifest` invocation does.
    manifests = []
    timings = []
    chunks = [int(n) for n in os.environ.get("PROVING_CHUNKS", "1,2,3,4,5,6,7").split(",")]
    for n in chunks:
        source = bundles / f"chunk{n}"
        deadline = time.monotonic() + 3 * 3600
        while not source.is_dir():
            assert time.monotonic() < deadline, f"bundle {n} never appeared"
            time.sleep(15)
        target = tmp_path / f"chunk{n}"
        shutil.copytree(source, target)
        body = json.loads((target / "manifest.json").read_text())
        assert body["policy_digest"] == LIVE_POLICY
        body["policy_digest"] = policy
        (target / "manifest.json").write_text(canonical(body) + "\n")
        manifests.append((n, target / "manifest.json", body))
        started = time.monotonic()
        result = execute_manifest(
            store,
            coordinator,
            path=str(target / "manifest.json"),
            run_id=str(uuid4()),
            stage="mastering",
            limit=1000,
        )
        timings.append(
            {
                "chunk": n,
                "seconds": round(time.monotonic() - started, 1),
                "records": body["scope"]["selected_records"],
                "records_processed": result.get("records_processed"),
                "unresolved_reviews": result.get("unresolved_reviews"),
            }
        )
        print(json.dumps(timings[-1]), flush=True)
    with database.application.connect() as conn:
        after_first = counts(conn)
        outcome = records(conn)
    with database.admin.connect() as conn:
        functions = [
            {"function": r[0], "calls": r[1], "self_ms": round(r[2]), "total_ms": round(r[3])}
            for r in conn.execute(
                text(
                    "SELECT schemaname||'.'||funcname, calls, self_time, total_time "
                    "FROM pg_stat_user_functions ORDER BY self_time DESC LIMIT 12"
                )
            )
        ]

    for _, path, _ in manifests:
        execute_manifest(
            store,
            coordinator,
            path=str(path),
            run_id=str(uuid4()),
            stage="mastering",
            limit=1000,
        )
    with database.application.connect() as conn:
        after_second = counts(conn)
        duplicate_ciks = conn.execute(
            text(
                "SELECT reading->'identifiers'->>'cik', count(DISTINCT entity_id) "
                "FROM mdm_v2.stage_record WHERE entity_id IS NOT NULL "
                "GROUP BY 1 HAVING count(DISTINCT entity_id) > 1"
            )
        ).all()
        shared_companies = conn.execute(
            text(
                "SELECT entity_id, count(*) FROM mdm_v2.stage_record "
                "WHERE entity_id IS NOT NULL GROUP BY 1 HAVING count(*) > 1"
            )
        ).all()
        review_sample = [
            r[0]
            for r in conn.execute(
                text(
                    "SELECT body FROM mdm_v2.projection WHERE object_type='review' "
                    "AND body->'open'='true'::jsonb LIMIT 3"
                )
            )
        ]

    report = {
        "ticket": "company mastering 05, Phase 1",
        "chunks": chunks,
        "manifest_sha256": corpus,
        "live_policy": LIVE_POLICY,
        "candidate_policy_for_approval": {
            "version": VERSION,
            "digest": digest(pending_body),
            "approval_fields": PENDING,
        },
        "registered_for_the_run": {"digest": policy, "approval_fields": proving},
        "bundles": [
            {
                "chunk": n,
                "publication_key": b["batches"][0]["input"]["publication"][
                    "publication_key"
                ],
                "records": b["scope"]["selected_records"],
                "records_sha256": b["batches"][0]["input"]["sha256"],
            }
            for n, _, b in manifests
        ],
        "timings": timings,
        "sql_functions_first_pass": functions,
        "after_first_pass": after_first,
        "after_second_pass": after_second,
        "second_pass_changed_nothing": after_first == after_second,
        "cik_on_more_than_one_company": [list(r) for r in duplicate_ciks],
        "company_with_more_than_one_sec_record": [
            [str(r[0]), r[1]] for r in shared_companies
        ],
        "review_sample": review_sample,
        "records": outcome,
    }
    out.write_text(json.dumps(report, sort_keys=True, indent=1, default=str) + "\n")
    # The exact body the operator is asked to approve (ticket 06), in the
    # canonical form its digest is taken over.
    (out.parent / "candidate-policy.json").write_text(canonical(pending_body) + "\n")
    print(
        json.dumps(
            {k: report[k] for k in report if k not in ("records", "review_sample")},
            indent=1,
            default=str,
        )
    )
    assert report["second_pass_changed_nothing"]
