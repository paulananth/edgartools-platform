"""pipeline-resumability ticket 02: MdmRun's company-step resume support.

run_companies() previously re-resolved all companies from scratch on every
call, with no way to skip already-done CIKs on a restart. These tests cover
the new resume_ledger_run_id/run_id parameters: a one-time frozen CIK
snapshot plus batched succeeded-CIK outcome flushes (see
edgar_warehouse.mdm.company_resume), fail-closed behavior on a bogus resume
pointer, and the resume+limit/issuer_ciks mutual-exclusion guard.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional
from unittest.mock import patch

import pytest
from sqlalchemy import select

from edgar_warehouse.application.errors import WarehouseRuntimeError
from edgar_warehouse.mdm.company_resume import (
    ResumeRunNotFoundError,
    outcomes_prefix,
    read_succeeded_ciks,
    snapshot_path,
)
from edgar_warehouse.mdm.database import MdmCompany
from edgar_warehouse.mdm.pipeline import MDMPipeline

from tests.mdm.test_run_companies_concurrency import (
    _companies_fixture,
    _seeded_sqlite_session,
    StubSilver,
)


def _snapshot_ciks(bronze_root: Path, run_id: str) -> list[int]:
    text = (bronze_root / snapshot_path(run_id)).read_text(encoding="utf-8")
    return [json.loads(line)["cik"] for line in text.splitlines() if line.strip()]


class TestFreshRunWritesSnapshotAndFlushesOutcomes:
    def test_fresh_run_creates_snapshot_and_flushes_all_ciks(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        monkeypatch.setenv("WAREHOUSE_BRONZE_ROOT", str(tmp_path))
        session = _seeded_sqlite_session(static_pool=True)
        silver = StubSilver(_companies_fixture(5))
        pipeline = MDMPipeline(session=session, silver=silver)

        processed = pipeline.run_companies(run_id="fresh-run-1")

        assert processed == 5
        assert _snapshot_ciks(tmp_path, "fresh-run-1") == [900000 + i for i in range(5)]
        succeeded = read_succeeded_ciks(bronze_root=str(tmp_path), run_id="fresh-run-1")
        assert succeeded == {900000 + i for i in range(5)}

    def test_no_run_id_and_no_resume_ledger_run_id_skips_resume_infra(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Neither flag given (e.g. an ad-hoc local `mdm run company` call) --
        behaves exactly like before this ticket, no snapshot/markers written."""
        monkeypatch.setenv("WAREHOUSE_BRONZE_ROOT", str(tmp_path))
        session = _seeded_sqlite_session(static_pool=True)
        silver = StubSilver(_companies_fixture(3))
        pipeline = MDMPipeline(session=session, silver=silver)

        processed = pipeline.run_companies()

        assert processed == 3
        assert not (tmp_path / "reference" / "mdm_company_resume").exists()


class TestExplicitResumeSkipsAlreadySucceeded:
    def test_resume_only_resolves_remaining_ciks(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("WAREHOUSE_BRONZE_ROOT", str(tmp_path))
        session = _seeded_sqlite_session(static_pool=True)
        silver = StubSilver(_companies_fixture(5))
        pipeline = MDMPipeline(session=session, silver=silver)

        # First attempt: freeze the snapshot, resolve everything.
        pipeline.run_companies(run_id="original-run")
        first_entity_ids = {
            row.cik: row.entity_id for row in session.execute(select(MdmCompany)).scalars().all()
        }
        assert len(first_entity_ids) == 5

        # Simulate a stop-after-partial-progress: only 3 of 5 actually
        # "succeeded" from the ledger's point of view (overwrite the
        # all-succeeded outcome file from the first call with a partial one).
        import shutil

        shutil.rmtree(tmp_path / outcomes_prefix("original-run"))
        from edgar_warehouse.mdm.company_resume import write_outcome_batch

        write_outcome_batch(
            bronze_root=str(tmp_path), run_id="original-run", batch_id="partial",
            ciks=[900000, 900001, 900002],
        )

        # Resume: only the 2 remaining CIKs should be re-queried/resolved.
        # StubSilver matches by SQL substring only (ignores params), so this
        # wrapper filters the canned rows by the actual CIK params passed --
        # otherwise the stub would return all 5 rows regardless of the WHERE
        # clause and mask the real filtering this test is checking.
        fetched_ciks: list[list[int]] = []
        real_fetch = silver.fetch

        def _tracking_fetch(sql: str, params: Optional[list[Any]] = None):
            is_scoped_company_query = (
                "WHERE cik IN" in sql and "FROM sec_company " in sql and "ticker" not in sql
            )
            if is_scoped_company_query:
                fetched_ciks.append(list(params or []))
                rows = real_fetch(sql, None)
                wanted = {int(c) for c in (params or [])}
                return [row for row in rows if row["cik"] in wanted]
            return real_fetch(sql, params)

        with patch.object(silver, "fetch", side_effect=_tracking_fetch):
            processed = pipeline.run_companies(resume_ledger_run_id="original-run")

        assert processed == 2
        assert fetched_ciks == [[900003, 900004]]
        # Existing entities untouched; all 5 still resolved, no duplicates.
        second_entity_ids = {
            row.cik: row.entity_id for row in session.execute(select(MdmCompany)).scalars().all()
        }
        assert len(second_entity_ids) == 5
        for cik in (900000, 900001, 900002):
            assert second_entity_ids[cik] == first_entity_ids[cik]

    def test_resume_when_everything_already_succeeded_resolves_nothing(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        monkeypatch.setenv("WAREHOUSE_BRONZE_ROOT", str(tmp_path))
        session = _seeded_sqlite_session(static_pool=True)
        silver = StubSilver(_companies_fixture(3))
        pipeline = MDMPipeline(session=session, silver=silver)

        pipeline.run_companies(run_id="original-run")
        processed = pipeline.run_companies(resume_ledger_run_id="original-run")

        assert processed == 0


class TestResumeFailsClosed:
    def test_bogus_resume_pointer_raises(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("WAREHOUSE_BRONZE_ROOT", str(tmp_path))
        session = _seeded_sqlite_session(static_pool=True)
        silver = StubSilver(_companies_fixture(3))
        pipeline = MDMPipeline(session=session, silver=silver)

        with pytest.raises(ResumeRunNotFoundError):
            pipeline.run_companies(resume_ledger_run_id="never-existed")

    def test_resume_without_bronze_root_env_var_raises(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.delenv("WAREHOUSE_BRONZE_ROOT", raising=False)
        session = _seeded_sqlite_session(static_pool=True)
        silver = StubSilver(_companies_fixture(3))
        pipeline = MDMPipeline(session=session, silver=silver)

        with pytest.raises(WarehouseRuntimeError, match="WAREHOUSE_BRONZE_ROOT"):
            pipeline.run_companies(resume_ledger_run_id="some-run")


class TestResumeMutualExclusion:
    def test_resume_with_limit_raises(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("WAREHOUSE_BRONZE_ROOT", str(tmp_path))
        session = _seeded_sqlite_session(static_pool=True)
        silver = StubSilver(_companies_fixture(3))
        pipeline = MDMPipeline(session=session, silver=silver)

        with pytest.raises(WarehouseRuntimeError, match="full-universe"):
            pipeline.run_companies(limit=1, resume_ledger_run_id="some-run")

    def test_resume_with_issuer_ciks_raises(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("WAREHOUSE_BRONZE_ROOT", str(tmp_path))
        session = _seeded_sqlite_session(static_pool=True)
        silver = StubSilver(_companies_fixture(3))
        pipeline = MDMPipeline(session=session, silver=silver)

        with pytest.raises(WarehouseRuntimeError, match="full-universe"):
            pipeline.run_companies(issuer_ciks=[900000], resume_ledger_run_id="some-run")


class TestBatchedOutcomeFlushCadence:
    def test_flushes_mid_run_not_only_at_the_end(self, tmp_path: Path, monkeypatch) -> None:
        """With a forced interval of 1, every completed row should trigger its
        own flush (in addition to the final catch-all flush) -- proves the
        periodic mid-loop _flush_pending() call is reachable, not just the
        unconditional one after the executor block."""
        monkeypatch.setenv("WAREHOUSE_BRONZE_ROOT", str(tmp_path))
        session = _seeded_sqlite_session(static_pool=True)
        silver = StubSilver(_companies_fixture(4))
        pipeline = MDMPipeline(session=session, silver=silver)

        with patch("edgar_warehouse.mdm.pipeline._progress_log_interval", return_value=1):
            processed = pipeline.run_companies(run_id="flush-cadence-run")

        assert processed == 4
        outcome_dir = tmp_path / outcomes_prefix("flush-cadence-run")
        # SQLite guard forces max_workers=1 here, so with interval=1 each of
        # the 4 rows flushes its own batch file (sequential, deterministic).
        assert len(list(outcome_dir.glob("*.json"))) == 4
        assert read_succeeded_ciks(bronze_root=str(tmp_path), run_id="flush-cadence-run") == {
            900000, 900001, 900002, 900003,
        }


class TestResumePartialFailureStillFlushesSucceededWork:
    def test_flush_happens_even_when_a_later_row_raises(self, tmp_path: Path, monkeypatch) -> None:
        """If row N+1 raises, rows 1..N that already committed successfully
        must still be flushed to the outcome ledger -- otherwise a resume
        after this failure would needlessly re-resolve already-done work
        (still safe/idempotent, just not actually resumed)."""
        monkeypatch.setenv("WAREHOUSE_BRONZE_ROOT", str(tmp_path))
        session = _seeded_sqlite_session(static_pool=True)
        silver = StubSilver(_companies_fixture(3))
        pipeline = MDMPipeline(session=session, silver=silver)

        call_count = {"n": 0}
        from edgar_warehouse.mdm.resolvers import CompanyResolver

        real_resolve_one = CompanyResolver.resolve_one

        def _flaky_resolve_one(self, *args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 3:
                raise RuntimeError("boom")
            return real_resolve_one(self, *args, **kwargs)

        with patch(
            "edgar_warehouse.mdm.pipeline.CompanyResolver.resolve_one",
            new=_flaky_resolve_one,
        ):
            with pytest.raises(RuntimeError, match="boom"):
                pipeline.run_companies(run_id="partial-failure-run")

        succeeded = read_succeeded_ciks(bronze_root=str(tmp_path), run_id="partial-failure-run")
        assert len(succeeded) == 2
