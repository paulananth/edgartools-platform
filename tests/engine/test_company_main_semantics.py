"""Actual Company main contract acceptance and generic document assertions."""
from copy import deepcopy
import json

import pytest

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.rules import files
from edgar_warehouse.rules.source_engine import SourceRejected
from edgar_warehouse.workers import source_read
from scripts.qualification.audit_company_main_semantics import audit, CONTEXT


def test_main_output_and_refusal_matrix_has_exact_typed_parity():
    result = audit()
    assert result["cases"] == 449
    assert result["difference_count"] == 0, result["differences"]
    assert result["accepted"] == 395 and result["refused"] == 54


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
