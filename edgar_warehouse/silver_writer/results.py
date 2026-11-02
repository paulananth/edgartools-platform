"""The data quality results a silver load leaves for the catalog.

`checks.run` reports, per delivery, the rows each check failed. A load that is
given a results file (`land(..., results=path)`, or the `QUALITY_RESULTS_FILE`
environment variable) keeps the latest report of every check in it, one entry
per catalog case name (`<table>.<check id>`). `rules catalog publish --results`
sends each entry as that case's test result.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ENVIRONMENT = "QUALITY_RESULTS_FILE"


def load(path: Path) -> dict[str, dict]:
    """The recorded results by case name; none when the file does not exist."""
    path = Path(path)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))["results"]
    except (ValueError, KeyError, TypeError) as error:
        raise ValueError(f"{path} is not a quality results file ({type(error).__name__}); delete it and reload") from error


def record(path: Path, table: str, report: dict, at: datetime | None = None) -> None:
    """Keep the latest report of each of `table`'s checks in the file."""
    if not report:
        return
    at = (at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    results = load(path)
    for check, outcome in sorted(report["checks"].items()):
        results[f"{table}.{check}"] = {
            "table": table, "check": check, "on_fail": outcome["on_fail"], "at": at.isoformat(),
            "rows_checked": report["rows_checked"], "rows_failed": outcome["rows_failed"]}
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"results": results}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
