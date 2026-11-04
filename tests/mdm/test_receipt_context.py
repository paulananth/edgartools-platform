"""A step's context value may be the document's own receipt hash (ticket 177, slice 1). Every name here is invented."""
import hashlib
from copy import deepcopy

import pytest

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.mdm import target_manifest
from edgar_warehouse.rules import files
from tests.mdm.test_ownership_target import SOURCE, capture


def plan(monkeypatch, tmp_path, context):
    real = files.source

    def changed(name, *args, **kwargs):
        reading = deepcopy(real(name, *args, **kwargs))
        if name == SOURCE:
            steps = reading["bookkeeping"]["targets"]["mastering"]["steps"]
            steps[0]["input"]["context"] = context
        return reading
    monkeypatch.setattr(target_manifest.rules_files, "source", changed)
    return target_manifest.write_manifest(**capture(tmp_path, [1]))


def test_the_context_holds_the_documents_receipt_hash(monkeypatch, tmp_path):
    report = plan(monkeypatch, tmp_path, {"accession_number": {"receipt": "sha256"}})
    store = Artifacts()
    (read,) = store.json(report["manifest"])["steps"]["read"]
    (artifact,) = store.json(read["input"])["artifacts"]
    raw = b"an invented submission 1"
    assert store.json(artifact["context"])["values"] == {"accession_number": hashlib.sha256(raw).hexdigest()}


@pytest.mark.parametrize("context", [{"accession_number": {"receipt": "key"}}, {"accession_number": {"receipt": "sha256", "x": 1}},
                                     {"accession_number": {"receipt": 1}}])
def test_another_receipt_field_is_refused(monkeypatch, tmp_path, context):
    with pytest.raises(Exception, match="context names values"):
        plan(monkeypatch, tmp_path, context)
