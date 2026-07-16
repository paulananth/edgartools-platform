from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "verify-relationship-generations.sh"

ALL_STAGES = [
    "preflight",
    "watermark",
    "plan",
    "build-partitions",
    "fan-in",
    "activate-generation",
    "sync-graph",
    "verify-graph",
    "graph-activate",
    "coverage-report",
    "hosted-e2e",
    "retry-failed",
    "entity-merge",
    "graph-rollback",
]


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _fake_aws(running_executions: str = "0") -> str:
    return f"""#!/usr/bin/env bash
args="$*"
if [[ "$args" == *"list-executions"* ]]; then
  echo "{running_executions}"
  exit 0
fi
echo "unexpected aws invocation: $args" >&2
exit 1
"""


def _fake_uv(fail_subcommand: str = "") -> str:
    # Dispatches on argv content rather than executing anything real, except
    # for the local-filesystem manifest-read helper calls (`uv run [--extra X]
    # python3 -c ...`), which are passed through to a real python3 -- those
    # only touch WAREHOUSE_BRONZE_ROOT on local disk, never the network.
    return f"""#!/usr/bin/env bash
args="$*"

fail_subcommand="{fail_subcommand}"
if [[ -n "$fail_subcommand" && "$args" == *"mdm $fail_subcommand"* ]]; then
  echo '{{"status": "failed", "reason": "injected test failure"}}' >&2
  exit 1
fi

if [[ "$args" == *"edgar-warehouse mdm generation-plan"* ]]; then
  run_id=""
  prev=""
  for a in "$@"; do
    if [[ "$prev" == "--run-id" ]]; then run_id="$a"; fi
    prev="$a"
  done
  python3 -c "
import json
import os
from pathlib import Path

bronze = Path(os.environ['WAREHOUSE_BRONZE_ROOT'])
run_dir = bronze / 'reference' / 'mdm_generation' / 'runs' / '$run_id'
run_dir.mkdir(parents=True, exist_ok=True)
(run_dir / 'generation.json').write_text(json.dumps({{'generation_id': 'fake-generation-1'}}))
(run_dir / 'partitions.jsonl').write_text(
    json.dumps({{'partition_id': 'fake-partition-1', 'kind': 'node', 'type_name': 'company', 'shard_index': 0}}) + chr(10)
)
"
  echo '{{"generation_id": "fake-generation-1", "partition_count": 1}}'
  exit 0
fi

if [[ "$args" == *"edgar-warehouse mdm"* ]]; then
  echo '{{"status": "ok"}}'
  exit 0
fi

if [[ "$args" == *"neo4j-snowflake-migration.py"* ]]; then
  echo '{{"output_dir": "fake", "files": [], "snow_connection": "snowconn", "applied": [], "external_neo4j": false, "note": "fake"}}'
  exit 0
fi

if [[ "$1" == "run" ]]; then
  shift
  while [[ "$1" == "--extra" ]]; do shift 2; done
  exec "$@"
fi

echo "unexpected uv invocation: $args" >&2
exit 1
"""


def _read_evidence(evidence_dir: Path) -> list[dict]:
    lines = (evidence_dir / "evidence.jsonl").read_text().splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def test_requires_exact_dev_connection_when_unset(tmp_path: Path) -> None:
    env = {k: v for k, v in os.environ.items() if k != "SNOW_CONNECTION"}
    result = subprocess.run(
        ["bash", str(SCRIPT), "--all"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "SNOW_CONNECTION must be exactly snowconn" in result.stderr
    # No evidence directory should ever be created -- the guard fires before
    # anything else, so nothing was attempted, let alone recorded.
    assert not (tmp_path / "evidence.jsonl").exists()


def test_requires_exact_dev_connection_when_wrong(tmp_path: Path) -> None:
    aws = tmp_path / "aws"
    uv = tmp_path / "uv"
    _write_executable(aws, "#!/usr/bin/env bash\necho 'AWS SHOULD NOT HAVE BEEN INVOKED' >&2\nexit 99\n")
    _write_executable(uv, "#!/usr/bin/env bash\necho 'UV SHOULD NOT HAVE BEEN INVOKED' >&2\nexit 99\n")
    result = subprocess.run(
        ["bash", str(SCRIPT), "--all"],
        cwd=ROOT,
        env={**os.environ, "SNOW_CONNECTION": "wrong", "AWS_BIN": str(aws), "UV_BIN": str(uv)},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "SNOW_CONNECTION must be exactly snowconn" in result.stderr
    # Neither fake binary's sentinel text appears -- proves the guard fires
    # before any AWS or Snowflake-touching command is ever invoked.
    assert "SHOULD NOT HAVE BEEN INVOKED" not in (result.stdout + result.stderr)


def test_help_lists_every_stage(tmp_path: Path) -> None:
    result = subprocess.run(
        ["bash", str(SCRIPT), "--help"],
        cwd=ROOT,
        env={**os.environ, "SNOW_CONNECTION": "snowconn"},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    for stage in ALL_STAGES:
        assert stage in result.stdout, f"stage {stage!r} missing from --help output"


def test_missing_all_or_stage_fails_before_any_command(tmp_path: Path) -> None:
    result = subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=ROOT,
        env={**os.environ, "SNOW_CONNECTION": "snowconn"},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "either --all or --stage <name> is required" in result.stderr


def test_optional_stages_skip_cleanly_without_required_args(tmp_path: Path) -> None:
    evidence_dir = tmp_path / "evidence"
    result = subprocess.run(
        [
            "bash",
            str(SCRIPT),
            "--stage",
            "entity-merge",
            "--evidence-dir",
            str(evidence_dir),
        ],
        cwd=ROOT,
        env={**os.environ, "SNOW_CONNECTION": "snowconn"},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    records = _read_evidence(evidence_dir)
    assert len(records) == 1
    assert records[0]["stage"] == "entity-merge"
    assert "SKIPPED" in records[0]["output"]


def test_redaction_strips_credentials_before_evidence_is_written(tmp_path: Path) -> None:
    uv = tmp_path / "uv"
    _write_executable(
        uv,
        """#!/usr/bin/env bash
echo 'DSN=postgresql://user:hunter2@dbhost:5432/mdm'
echo 'PASSWORD: "s3cr3t-value"'
exit 0
""",
    )
    evidence_dir = tmp_path / "evidence"
    result = subprocess.run(
        [
            "bash",
            str(SCRIPT),
            "--stage",
            "watermark",
            "--evidence-dir",
            str(evidence_dir),
        ],
        cwd=ROOT,
        env={**os.environ, "SNOW_CONNECTION": "snowconn", "UV_BIN": str(uv)},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    evidence_text = (evidence_dir / "evidence.jsonl").read_text()
    assert "hunter2" not in evidence_text
    assert "s3cr3t-value" not in evidence_text
    assert "[REDACTED]" in evidence_text
    # Also never on stdout/stderr the operator sees.
    assert "hunter2" not in result.stdout
    assert "s3cr3t-value" not in result.stdout


def test_full_rehearsal_chain_runs_every_stage_in_order(tmp_path: Path) -> None:
    aws = tmp_path / "aws"
    uv = tmp_path / "uv"
    bronze_root = tmp_path / "bronze"
    bronze_root.mkdir()
    evidence_dir = tmp_path / "evidence"
    _write_executable(aws, _fake_aws())
    _write_executable(uv, _fake_uv())

    result = subprocess.run(
        [
            "bash",
            str(SCRIPT),
            "--all",
            "--run-id",
            "test-run-1",
            "--evidence-dir",
            str(evidence_dir),
            "--entity-merge-keep",
            "entity-keep-1",
            "--entity-merge-discard",
            "entity-discard-1",
            "--rollback-to-generation-id",
            "prior-generation-1",
        ],
        cwd=ROOT,
        env={
            **os.environ,
            "SNOW_CONNECTION": "snowconn",
            "AWS_BIN": str(aws),
            "UV_BIN": str(uv),
            "WAREHOUSE_BRONZE_ROOT": str(bronze_root),
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "RUN_ID=test-run-1" in result.stdout
    assert f"EVIDENCE_FILE={evidence_dir}/evidence.jsonl" in result.stdout

    records = _read_evidence(evidence_dir)
    recorded_stages = [record["stage"] for record in records]
    for stage in ALL_STAGES:
        assert stage in recorded_stages, f"stage {stage!r} never ran: {recorded_stages}"
    # Neither optional stage was skipped, since their args were supplied.
    entity_merge_records = [r for r in records if r["stage"] == "entity-merge"]
    assert all("SKIPPED" not in r["output"] for r in entity_merge_records)
    rollback_records = [r for r in records if r["stage"] == "graph-rollback"]
    assert all("SKIPPED" not in r["output"] for r in rollback_records)


def test_failed_stage_halts_all_and_never_reaches_activation(tmp_path: Path) -> None:
    aws = tmp_path / "aws"
    uv = tmp_path / "uv"
    bronze_root = tmp_path / "bronze"
    bronze_root.mkdir()
    evidence_dir = tmp_path / "evidence"
    _write_executable(aws, _fake_aws())
    # fan-in fails; nothing past it (activate-generation, sync-graph,
    # verify-graph, graph-activate, ...) should ever be invoked -- a failed
    # generation must never reach the active-pointer stages.
    _write_executable(uv, _fake_uv(fail_subcommand="generation-fan-in"))

    result = subprocess.run(
        [
            "bash",
            str(SCRIPT),
            "--all",
            "--run-id",
            "test-run-fail",
            "--evidence-dir",
            str(evidence_dir),
        ],
        cwd=ROOT,
        env={
            **os.environ,
            "SNOW_CONNECTION": "snowconn",
            "AWS_BIN": str(aws),
            "UV_BIN": str(uv),
            "WAREHOUSE_BRONZE_ROOT": str(bronze_root),
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "never change the active pointer" in result.stderr

    records = _read_evidence(evidence_dir)
    recorded_stages = [record["stage"] for record in records]
    assert "fan-in" in recorded_stages
    for later_stage in ("activate-generation", "sync-graph", "verify-graph", "graph-activate"):
        assert later_stage not in recorded_stages, (
            f"stage {later_stage!r} ran after fan-in failed: {recorded_stages}"
        )


def test_script_contains_no_neo4j_bolt_or_aura_credentials(tmp_path: Path) -> None:
    script_text = SCRIPT.read_text()
    for token in ("NEO4J_URI", "NEO4J_PASSWORD", "bolt://", "neo4j+s://"):
        assert token not in script_text
