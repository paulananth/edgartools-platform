"""Actual Company main contract acceptance and generic document assertions.

The finite matrix (`fixtures/company-main-matrix.json`, written once from the old
loaders) holds each case's input and its tables, or that it is refused; a
table row keeps only the values that differ from that table's defaults."""
from copy import deepcopy
import json

import pytest

from pathlib import Path

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.control_contract import digest
from edgar_warehouse.rules import files
from edgar_warehouse.rules.source_engine import SourceEngine, SourceRejected
from edgar_warehouse.workers import source_read

CONTEXT = {
    "cik": 320193, "sync_run_id": "qualification", "raw_object_id": "0" * 64,
    "load_mode": "default", "recent_limit": None, "last_synced_at": "2026-10-05T00:00:00Z",
}
MATRIX = json.loads((Path(__file__).parent / "fixtures/company-main-matrix.json").read_text())
RUN = {key: CONTEXT[key] for key in ("cik", "sync_run_id", "raw_object_id", "load_mode")}
DEFAULTS = {
    "company": {**RUN, **dict.fromkeys(["entity_name", "entity_type", "sic", "sic_description",
                                        "state_of_incorporation", "state_of_incorporation_desc",
                                        "fiscal_year_end", "ein", "description", "category"]),
                "last_sync_run_id": "qualification", "last_synced_at": CONTEXT["last_synced_at"]},
    "filings": {**RUN, **dict.fromkeys(["accession_number", "form", "filing_date", "report_date",
                                        "acceptance_datetime", "act", "file_number", "film_number", "items",
                                        "size", "primary_document", "primary_doc_desc"]),
                "is_xbrl": False, "is_inline_xbrl": False},
    "addresses": {"cik": 320193, "last_sync_run_id": "qualification", "business_address": None},
}


def audit(contract=None):
    """The cases where the engine's tables, or its refusal, differ from the matrix."""
    engine = SourceEngine(contract if contract is not None else files.source("sec.submissions.company"))
    differences = []
    for case in MATRIX:
        context = {**CONTEXT, "recent_limit": case["recent_limit"]}
        try:
            found = engine.read(json.dumps(case["input"]).encode(), context=context)
            outcome = None if found.deferred else found.tables
        except SourceRejected:
            outcome = "refused"
        expected = "refused" if case.get("refused") else {
            name: [{**DEFAULTS[name], **row} for row in rows] for name, rows in case["tables"].items()}
        if digest(outcome) != digest(expected):
            differences.append(case)
    return {"cases": len(MATRIX), "difference_count": len(differences), "differences": differences,
            "refused": sum(1 for case in MATRIX if case.get("refused"))}


def test_main_output_and_refusal_matrix_has_exact_typed_parity():
    result = audit()
    assert result["cases"] == 449
    assert result["difference_count"] == 0, result["differences"]
    assert result["refused"] == 54


@pytest.mark.parametrize("fault", ["root-assertion", "address-assertion", "business-selection", "place-coercion"])
def test_deliberate_configuration_faults_are_detected(fault):
    contract = deepcopy(files.source("sec.submissions.company"))
    read = contract["read"]
    if fault == "root-assertion":
        read["assertions"].pop(0)
    elif fault == "address-assertion":
        read["assertions"].pop(1)
    elif fault == "business-selection":
        read["tables"]["addresses"]["each"] = "addresses.business"
    else:
        key = read["tables"]["addresses"]["columns"]["business_address"]["object"]["fields"]["country"]["lookup"]["key"]
        key["choose"]["then"] = {"value": {"path": "stateOrCountry"}}
    assert audit(contract)["difference_count"] > 0


@pytest.mark.parametrize("payload", [None, [], "x", {"addresses": None}, {"addresses": []}])
def test_document_shape_failure_produces_no_worker_output(tmp_path, payload):
    store = Artifacts()
    raw = store.put_bytes((tmp_path / "source.json").as_uri(), json.dumps(payload).encode())
    context = store.put(tmp_path.as_uri(), {"version": 1, "input": raw, "values": CONTEXT})
    contract = store.put(tmp_path.as_uri(), files.source("sec.submissions.company"))
    manifest = store.put(tmp_path.as_uri(), {"version": 2, "contract": contract,
                                          "artifacts": [{"input": raw, "context": context}]})
    output = tmp_path / "reading.json"
    with pytest.raises(SourceRejected, match="assertion_failed"):
        source_read.execute({"input": manifest, "output": output.as_uri(), "checks": ["source.output"]}, store)
    assert not output.exists()
