"""End-to-end CLI coverage for Ticket 20's registry-* mdm subcommands."""

from __future__ import annotations

import json

import pytest

from edgar_warehouse.acquisition.models import AcquisitionBase
from edgar_warehouse.cli import build_parser


@pytest.fixture()
def _acquisition_db(tmp_path, monkeypatch: pytest.MonkeyPatch) -> str:
    from sqlalchemy import create_engine

    db_path = tmp_path / "mdm.db"
    url = f"sqlite:///{db_path}"
    AcquisitionBase.metadata.create_all(create_engine(url))
    monkeypatch.setenv("MDM_DATABASE_URL", url)
    return url


def _run(args_list: list[str]):
    parser = build_parser()
    args = parser.parse_args(args_list)
    return args, args.handler(args)


def test_registry_status_reports_no_active_version_before_activation(
    _acquisition_db, capsys: pytest.CaptureFixture[str]
) -> None:
    _, exit_code = _run(["mdm", "registry-status"])
    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"active": None}


def test_open_draft_then_activate_via_cli(
    tmp_path, _acquisition_db, capsys: pytest.CaptureFixture[str]
) -> None:
    coverage_path = tmp_path / "coverage.json"
    coverage_path.write_text(
        json.dumps(
            [
                {
                    "source_family": "filing_artifact",
                    "coverage_action": "add",
                    "in_scope_forms": ["3", "3/A", "4", "4/A", "5", "5/A"],
                    "acquisition_mode": "on_demand_fetch",
                    "completeness_policy": "non_empty_payload",
                    "discovery_policy": "daily_index_driven",
                    "required_producers": ["sec_raw_object"],
                    "coverage_start_date": "2026-01-01",
                    "catchup_required_through_date": "2026-01-01",
                }
            ]
        )
    )

    _, exit_code = _run(
        [
            "mdm",
            "registry-open-draft",
            "--coverage",
            str(coverage_path),
            "--operator-authorization-reference",
            "op-cli-1",
        ]
    )
    assert exit_code == 0
    draft_payload = json.loads(capsys.readouterr().out)
    assert draft_payload["status"] == "draft"
    version_id = draft_payload["version_id"]

    # Not yet caught up -- activation must block, not silently succeed.
    _, exit_code = _run(["mdm", "registry-activate", version_id])
    assert exit_code == 1
    blocked_payload = json.loads(capsys.readouterr().out)
    assert blocked_payload["status"] == "activation_blocked"
    assert "filing_artifact" in blocked_payload["blocker"]

    from edgar_warehouse.acquisition.registry_ledger import SourceRegistryLedger
    from edgar_warehouse.mdm.database import get_engine
    from datetime import date

    SourceRegistryLedger(get_engine()).record_catchup_progress(
        "filing_artifact", date(2026, 1, 1)
    )

    _, exit_code = _run(["mdm", "registry-activate", version_id])
    assert exit_code == 0
    activated_payload = json.loads(capsys.readouterr().out)
    assert activated_payload["status"] == "active"

    _, exit_code = _run(["mdm", "registry-status"])
    assert exit_code == 0
    status_payload = json.loads(capsys.readouterr().out)
    assert status_payload["active"]["version_id"] == version_id
    assert status_payload["active"]["coverage"][0]["source_family"] == "filing_artifact"
