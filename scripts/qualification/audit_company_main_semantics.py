"""Finite offline Company main output/refusal audit against retained loaders."""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from pathlib import Path

from edgar_warehouse.control_contract import digest
from tests.support.retired_submission_loaders.bronze_submission_extractors import (
    stage_address_loader, stage_company_loader, stage_recent_filing_loader,
)
from edgar_warehouse.mdm.clean.company_source import business_address
from edgar_warehouse.rules import files
from edgar_warehouse.rules.source_engine import SourceEngine, SourceRejected

CONTEXT = {
    "cik": 320193, "sync_run_id": "qualification", "raw_object_id": "0" * 64,
    "load_mode": "default", "recent_limit": None, "last_synced_at": "2026-10-05T00:00:00Z",
}
VALUES = [None, False, True, 0, 1, -1, 0.0, 9.9, "", " ", "x", [], {},
          [1], {"x": True}, {"street1": "x", "stateOrCountry": "DE"}]


def scalar(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"Unexpected historical scalar {type(value).__name__}")


def retained(payload, context):
    args = {key: context[key] for key in ("cik", "sync_run_id", "raw_object_id", "load_mode")}
    company = stage_company_loader(payload, **args)
    for row in company:
        row.update(last_sync_run_id=context["sync_run_id"], last_synced_at=context["last_synced_at"])
    filings = stage_recent_filing_loader(payload, **args, recent_limit=context["recent_limit"])
    addresses = [{"cik": context["cik"], "last_sync_run_id": context["sync_run_id"],
                  "business_address": business_address(row)}
                 for row in stage_address_loader(payload, **args) if row["address_type"] == "business"]
    return json.loads(json.dumps({"company": company, "filings": filings, "addresses": addresses},
                                default=scalar, allow_nan=False))


def cases():
    yield "empty", {}, CONTEXT
    for value in VALUES:
        yield "root", value, CONTEXT
    for field in ("name", "entityType", "sic", "sicDescription", "stateOfIncorporation",
                  "stateOfIncorporationDescription", "fiscalYearEnd", "ein", "description", "category"):
        for value in VALUES:
            yield f"company/{field}", {field: value}, CONTEXT
    for outer in VALUES:
        yield "addresses", {"addresses": outer}, CONTEXT
        yield "business", {"addresses": {"business": outer}}, CONTEXT
    for field in ("street1", "street2", "city", "zipCode", "stateOrCountry", "countryCode"):
        for value in VALUES:
            yield f"address/{field}", {"addresses": {"business": {field: value}}}, CONTEXT
    for value in VALUES:
        for limit in (None, 0, 1):
            context = {**CONTEXT, "recent_limit": limit}
            yield "filings", {"filings": value}, context
            yield "recent", {"filings": {"recent": value}}, context
            yield "anchor", {"filings": {"recent": {"accessionNumber": value, "form": ["10-K"]}}}, context


def outcome(call):
    try:
        return {"tables": call()}
    except (SourceRejected, AttributeError, TypeError, ValueError, KeyError, OverflowError) as error:
        return {"refused": getattr(error, "code", type(error).__name__)}


def audit(contract=None):
    engine = SourceEngine(contract if contract is not None else files.source("sec.submissions.company"))
    total = matched = accepted = refused = 0
    differences = []
    for label, payload, context in cases():
        total += 1
        old = outcome(lambda: retained(payload, context))
        def read():
            found = engine.read(json.dumps(payload, allow_nan=False).encode(), context=context)
            if found.deferred:
                raise ValueError("Unexpected deferred rows")
            return found.tables
        new = outcome(read)
        equal = ("refused" in old and "refused" in new) or (
            "tables" in old and "tables" in new and digest(old["tables"]) == digest(new["tables"]))
        accepted += "tables" in old
        refused += "refused" in old
        matched += equal
        if not equal:
            differences.append({"case": label, "input": payload, "recent_limit": context["recent_limit"],
                                "retained": old, "configured": new})
    return {"cases": total, "matched": matched, "accepted": accepted, "refused": refused,
            "difference_count": len(differences), "differences": differences,
            "comparison": "canonical typed tables and refusal decision; exception identity excluded",
            "universal_equivalence": False, "sec_requests": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--contract", type=Path, help="Optional explicit candidate contract")
    args = parser.parse_args()
    report = audit(files.load(args.contract) if args.contract else None)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "differences"}))


if __name__ == "__main__":
    main()
