"""Operator M0 smoke: publisher upsert, agent find, agent cannot write."""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value


def main() -> int:
    sys.path.insert(0, str(REPO_ROOT))
    _load_dotenv(Path(os.environ.get("ENV_FILE", REPO_ROOT / ".env")))
    publisher_uri = os.environ.get("MONGO_PUBLISHER_URI", "").strip()
    agent_uri = os.environ.get("MONGO_AGENT_URI", "").strip()
    if not publisher_uri or not agent_uri:
        print(
            "MONGO_PUBLISHER_URI and MONGO_AGENT_URI are required. "
            "Run provision-atlas-decision-projection.sh",
            file=sys.stderr,
        )
        return 1

    from edgar_warehouse.serving.mongo_decision_smoke import run_mongo_decision_smoke
    from edgar_warehouse.serving.mongo_decision_store import (
        PyMongoDecisionStore,
        mongo_client_from_uri,
    )
    from edgar_warehouse.serving.subject_bundle_read import build_issuer_subject_bundle
    from edgar_warehouse.serving.subject_feature_screen import build_subject_feature_screen
    from edgar_warehouse.serving.watermark_aggregator import (
        MemoryAlignmentStore,
        StageObservation,
    )

    wm = {
        "business_date": "2026-08-29",
        "gold_run_id": "g-1",
        "graph_generation_id": "gen-1",
        "silver_completeness_ok": True,
        "graph_parity_ok": True,
        "bronze_persist_used": False,
    }
    cik = 320193
    bundle = build_issuer_subject_bundle(subject_cik=cik, watermark_components=wm)
    screen = build_subject_feature_screen(
        warehouse_active_ciks=(cik,),
        mdm_active_ciks=(cik,),
        period_rows=(),
        watermark_components=wm,
    )
    issuer = {
        "subject_cik": cik,
        "bundle": bundle,
        "feature_screen_row": screen["rows"][0],
    }
    complete = StageObservation(complete=True, identity="g-1")
    graph = StageObservation(complete=True, identity="gen-1")

    result = run_mongo_decision_smoke(
        PyMongoDecisionStore(mongo_client_from_uri(publisher_uri)),
        PyMongoDecisionStore(mongo_client_from_uri(agent_uri)),
        alignment_store=MemoryAlignmentStore(),
        business_date="2026-08-29",
        cause_references=("operator-smoke",),
        silver=lambda _: complete,
        mdm=lambda _: complete,
        gold=lambda _: complete,
        graph=lambda _: graph,
        issuers=(issuer,),
        now=datetime.now(UTC),
    )
    print(
        "smoke: "
        f"written={result.documents_written} "
        f"agent_grade_find={result.agent_found_agent_grade} "
        f"agent_write_rejected={result.agent_write_rejected} "
        f"cik={result.found_cik}"
    )
    if (
        result.documents_written < 2
        or not result.agent_found_agent_grade
        or not result.agent_write_rejected
    ):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
