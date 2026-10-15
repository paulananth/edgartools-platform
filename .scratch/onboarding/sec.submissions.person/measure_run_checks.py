"""The run report checks (rebuild ticket 10, part 2) on the local copies.

Person feed 1 (every SEC submissions document) and the ownership feed's owners,
read through their contracts as a run would, then `quality.run_checks`. No
database; counts only (the repo is public).

  PYTHONPATH=. python .scratch/onboarding/sec.submissions.person/measure_run_checks.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parents[2]))


def _module(name: str, path: Path):
    """Each feed's own `proving_run.py`, under a name of its own."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


person_feed = _module("person_feed_run", HERE / "proving_run.py")
ownership = _module("ownership_run", HERE.parent / "sec.ownership" / "proving_run.py")

from edgar_warehouse.mdm.clean import quality  # noqa: E402
from edgar_warehouse.rules import files  # noqa: E402

AS_OF = "2026-10-14T00:00:00+00:00"


def main() -> None:
    policy = files.policy()
    assertions, deferred = [], []
    contract = files.mdm_contract("sec.submissions.person", person_feed.SOURCE_CODE)
    for receipt in person_feed.documents():
        kind, record = person_feed.read(receipt, contract, policy)
        (assertions if kind == "assertion" else deferred).append(
            record if kind == "assertion" else {"source_code": record["source_code"]})
    contract = files.mdm_contract("sec.ownership", ownership.OWNER)
    for sha, tables in ownership.filings():
        for row in tables["reporting_owner"]:
            member = f"{row['accession']}#{row['position']}"
            kind, record = ownership.read(row, ownership.OWNER, contract, policy,
                                          {"publication_key": f"{row['accession']}@{sha}", "revision": 1,
                                           "artifact_sha256": sha, "member": member, "record_locator": member})
            (assertions if kind == "assertions" else deferred).append(
                record if kind == "assertions" else {"source_code": record["source_code"]})
    checks = quality.run_checks([quality.profile(assertions, deferred)], as_of=AS_OF)
    out = HERE / "measure-run-checks.json"
    out.write_text(json.dumps({"as_of": AS_OF, "checks": checks}, indent=1, sort_keys=True) + "\n")
    print(json.dumps(checks, indent=1, sort_keys=True))


if __name__ == "__main__":
    main()
