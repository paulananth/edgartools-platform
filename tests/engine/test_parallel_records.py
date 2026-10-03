"""Configured parallel records through the binding and immutable worker protocol."""
import json
from pathlib import Path

import pytest

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.loaders.bronze_submission_extractors import stage_recent_filing_loader
from edgar_warehouse.rules import files
from edgar_warehouse.rules.source_engine import SourceEngine, SourceRejected
from edgar_warehouse.workers import source_read

CONTRACT = Path(__file__).parent / "fixtures" / "parallel-filings.yaml"


@pytest.mark.parametrize("forms", [["10-K", "8-K"], [" ", ""], [None], [], ["6-K", "20-F", "40-F"]])
def test_declared_projection_matches_the_old_loader_for_short_empty_and_extra_arrays(forms):
    payload = {"cik": "320193", "filings": {"recent": {"accessionNumber": ["a", "b"], "form": forms}}}
    old = stage_recent_filing_loader(payload, 320193, "fixture", "captured", "default")
    expected = [{key: row[key] for key in ("accession_number", "form")} for row in old]
    assert SourceEngine(files.load(CONTRACT)).read(json.dumps(payload).encode()).tables["filings"] == expected


def test_worker_and_verifier_read_the_declared_arrays_without_a_source_loader(tmp_path):
    store = Artifacts()
    contract = store.put_bytes((tmp_path / "contract.yaml").as_uri(), CONTRACT.read_bytes())
    data = store.put_bytes((tmp_path / "captured.json").as_uri(),
                          b'{"filings":{"recent":{"accessionNumber":["a","b"],"form":["10-K"]}}}')
    manifest = store.put(tmp_path.as_uri(), {"version": 1, "contract": contract, "artifacts": [data]})
    envelope = {"input": manifest, "output": (tmp_path / "reading.json").as_uri(), "checks": ["source.output"]}
    candidate = source_read.execute(envelope, store)
    assert source_read.verify({**envelope, "candidate": candidate}, store) == ({"source.output": True}, [])
    assert store.json(candidate)["artifacts"][0]["tables"]["filings"] == [
        {"accession_number": "a", "form": "10-K"}, {"accession_number": "b", "form": None}]


def test_native_binding_refuses_an_array_that_has_become_a_scalar():
    with pytest.raises(SourceRejected) as error:
        SourceEngine(files.load(CONTRACT)).read(b'{"filings":{"recent":{"accessionNumber":"a","form":[]}}}')
    assert error.value.code == "parallel_shape"
