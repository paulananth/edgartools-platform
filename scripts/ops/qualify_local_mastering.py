"""Qualify the rebuilt mastering paths on disposable local PostgreSQL 16.

Run from the repository: uv run --extra mdm --extra s3 python
scripts/ops/qualify_local_mastering.py --output-root <new-directory>.
No hosted connection is used. Missing prerequisites fail, never skip.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
IMAGE = "postgres:16-alpine"
# Each subprocess has its own five-minute budget. A timeout is a failure.
SUITES = (
    ("mastering", ["tests/integration/test_fresh_mastering_postgres.py"]),
    ("unit", ["tests/unit"]),
    ("mdm", ["tests/mdm"]),
    ("architecture", ["tests/architecture"]),
    ("integration", ["tests/integration", "--ignore=tests/integration/test_fresh_mastering_postgres.py"]),
)


def qualify(output_root: Path) -> bool:
    """Retain new evidence; never accept a stale report from another run."""
    output_root.mkdir(parents=True, exist_ok=False)
    report = {"scope": "local qualification only", "qualified": False,
              "started_at": datetime.now().astimezone().isoformat(), "steps": []}
    report_path = output_root / "report.json"

    def save():
        report_path.write_text(json.dumps(report, indent=2) + "\n")

    def run(name: str, argv: list[str], timeout: int) -> bool:
        began = time.monotonic()
        step = {"name": name, "passed": False, "elapsed_seconds": 0.0}
        report["steps"].append(step)
        save()
        print(f"Starting {name} (budget {timeout}s)", flush=True)
        try:
            with (output_root / f"{name}.log").open("w") as log:
                result = subprocess.run(argv, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                        timeout=timeout, check=False)
            step.update(returncode=result.returncode, passed=result.returncode == 0)
        except (OSError, subprocess.TimeoutExpired) as exc:
            step["error"] = type(exc).__name__
        finally:
            step["elapsed_seconds"] = round(time.monotonic() - began, 3)
            save()
        print(f"{name}: {'passed' if step['passed'] else 'failed'} ({step['elapsed_seconds']}s)", flush=True)
        return step["passed"]

    # Do not start, stop, inspect or prune other containers or volumes.
    if not run("docker", ["docker", "info", "--format", "{{.ServerVersion}}"], 30):
        return False
    if not run("postgres-image", ["docker", "image", "inspect", IMAGE], 30):
        return False
    for name, paths in SUITES:
        if not run(name, [sys.executable, "-m", "pytest", *paths, "-q", "--tb=short",
                          f"--junitxml={output_root / (name + '.xml')}"], 300):
            return False
        try:
            cases = ET.parse(output_root / (name + '.xml')).findall('.//testcase')
            if not cases or any(case.find('failure') is not None or case.find('error') is not None
                                or (name in {'mastering', 'integration'} and case.find('skipped') is not None)
                                for case in cases):
                raise ValueError('Missing cases, failed cases, or skipped PostgreSQL acceptance')
        except (OSError, ET.ParseError, ValueError) as exc:
            report['steps'][-1].update(passed=False, error=type(exc).__name__)
            save()
            return False
    scripts = sorted([*(ROOT / 'infra/scripts').rglob('*.sh'), *(ROOT / 'scripts').rglob('*.sh')])
    for index, script in enumerate(scripts, 1):
        if not run(f'shell-{index}', ['bash', '-n', str(script)], 30):
            return False
    report.update(qualified=True, finished_at=datetime.now().astimezone().isoformat())
    save()
    return True


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, required=True,
                        help="New evidence directory; existing directories are refused")
    args = parser.parse_args(argv)
    return 0 if qualify(args.output_root.resolve()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
