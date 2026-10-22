"""Engine vocabulary is configuration; new kinds need no entity-name branch."""
import copy
import json
import os
import subprocess
import shutil
import sys

import pytest

from edgar_warehouse.mdm.clean import catalog, execution
from edgar_warehouse.rules import files


def write(root, body):
    target = root / catalog.RELATIVE
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(files.dumps(body))


def test_configuration_is_part_of_the_execution_identity():
    assert catalog.path() in execution.runtime_files()
    assert catalog.path().is_file()


def test_invented_kind_profile_and_approval_floor_are_loaded_without_engine_edits(tmp_path):
    body = copy.deepcopy(catalog.CATALOG)
    body["kinds"].append("invented-kind")
    body["profiles"]["invented-profile"] = ["invented-kind"]
    body["accepted_bars"]["invented-kind"] = {"classification": {
        "min_precision": 0.97, "one_sided_confidence": 0.975}}
    shutil.copytree(files.ROOT, tmp_path, dirs_exist_ok=True)
    write(tmp_path, body)
    assert catalog.load(tmp_path) == body
    program = '''
from edgar_warehouse.mdm.clean.evidence import KINDS, PROFILE_KINDS, assertion, validate_assertion
from edgar_warehouse.mdm.clean.activation import check_policy
from edgar_warehouse.mdm.clean.store import Conflict
assert "invented-kind" in KINDS
assert PROFILE_KINDS["invented-profile"] == {"invented-kind"}
body = assertion(source_code="invented-source", record_key="invented-key", publication_key="invented-delivery",
                 revision=1, effective_at=None, kind="invented-kind", fields={})
validate_assertion(body)
bar = {"method":"wilson_lower_bound", "min_precision":0.97,"one_sided_confidence":0.975}
check_policy({"kinds":{"invented-kind":{"bars":{"classification":bar}}}})
try:
    check_policy({"kinds":{"invented-kind":{"bars":{"classification":{**bar,"min_precision":0.96}}}}})
except Conflict:
    pass
else:
    raise AssertionError("Configured approval floor was lowered")
'''
    result = subprocess.run([sys.executable, "-c", program], env={**os.environ, "EDGAR_RULES_ROOT": str(tmp_path)},
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("change", ["duplicate_kind", "unknown_profile_kind", "unknown_bar_kind", "bad_floor"])
def test_invalid_catalog_is_refused(tmp_path, change):
    body = copy.deepcopy(catalog.CATALOG)
    if change == "duplicate_kind": body["kinds"].append(body["kinds"][0])
    elif change == "unknown_profile_kind": body["profiles"]["invented"] = ["absent-kind"]
    elif change == "unknown_bar_kind": body["accepted_bars"]["absent-kind"] = {}
    else: body["accepted_bars"][body["kinds"][0]] = {"classification": {"min_precision": 1, "one_sided_confidence": 0.95}}
    write(tmp_path, body)
    with pytest.raises(ValueError): catalog.load(tmp_path)


@pytest.mark.parametrize("initial", ["selected", "fallback"])
def test_same_process_catalog_drift_is_refused_before_execution_identity(tmp_path, initial):
    shutil.copytree(files.ROOT, tmp_path, dirs_exist_ok=True)
    if initial == "fallback": (tmp_path / catalog.RELATIVE).unlink()
    program = '''
from edgar_warehouse.mdm.clean import catalog, execution
from edgar_warehouse.mdm.clean.activation import check_policy
from edgar_warehouse.rules import files
assert catalog.path().read_bytes() == catalog.LOADED_BYTES
selected = files.ROOT / catalog.RELATIVE
selected.parent.mkdir(parents=True, exist_ok=True)
selected.write_text(files.dumps(catalog.CATALOG) + "\\n# invented changed catalog\\n")
for action in (execution.runtime_files, lambda: check_policy({"kinds":{}})):
    try:
        action()
    except ValueError as error:
        assert "catalog changed after loading" in str(error)
    else:
        raise AssertionError("A changed catalog was fingerprinted or executed")
'''
    result = subprocess.run([sys.executable, "-c", program], env={**os.environ, "EDGAR_RULES_ROOT": str(tmp_path)},
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
