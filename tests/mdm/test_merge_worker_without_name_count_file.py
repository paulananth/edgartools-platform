"""A merge worker needs only its own source's rules: the Name Count file loads when the count is used."""
import os
import shutil
import subprocess
import sys

import pytest

from edgar_warehouse.rules import files

NAME_COUNT_FILE = "name-count-filer.yaml"


@pytest.fixture(scope="module")
def rules_without_the_file(tmp_path_factory):
    folder = tmp_path_factory.mktemp("rules") / "rules"
    shutil.copytree(files.ROOT, folder, ignore=shutil.ignore_patterns(NAME_COUNT_FILE))
    assert not list(folder.rglob(NAME_COUNT_FILE))
    return folder


def _python_with_rules(folder, code):
    return subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True,
                          env={**os.environ, "EDGAR_RULES_ROOT": str(folder)})


def test_what_the_merge_workers_load_imports_without_the_file(rules_without_the_file):
    # The workers import the execution module inside `execute`, for every source;
    # `runtime_files` imports every module a merge pins.
    done = _python_with_rules(rules_without_the_file,
                              "import edgar_warehouse.workers.mdm_merge, edgar_warehouse.workers.mdm_publish\n"
                              "from edgar_warehouse.mdm.clean import execution, matching\n"
                              "assert execution.runtime_files()")
    assert done.returncode == 0, done.stderr


def test_the_count_names_its_missing_file_when_it_is_used(rules_without_the_file):
    done = _python_with_rules(rules_without_the_file,
                              "from edgar_warehouse.mdm.clean import name_count\n"
                              "name_count._sec_population([('1', 'Invented Organization', [])])")
    assert done.returncode != 0 and NAME_COUNT_FILE in done.stderr
