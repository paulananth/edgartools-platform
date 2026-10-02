"""Run the actual journal from an isolated package, with domain imports denied."""

from pathlib import Path
import os
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP = '''
import importlib.abc
import sys

class JournalOnly(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        permitted = ("edgar_warehouse.change_journal", "edgar_warehouse.control_contract")
        if fullname.startswith("edgar_warehouse.") and not any(
            fullname == name or fullname.startswith(name + ".") for name in permitted
        ):
            raise ImportError("Journal domain dependency forbidden: " + fullname)
        if fullname.split(".")[0] in {"edgar", "pyarrow", "lxml", "ijson", "boto3"}:
            raise ImportError("Journal domain dependency forbidden: " + fullname)

sys.meta_path.insert(0, JournalOnly())
'''


def isolated_package(tmp_path):
    package = tmp_path / "edgar_warehouse"
    package.mkdir()
    shutil.copyfile(ROOT / "edgar_warehouse/__init__.py", package / "__init__.py")
    shutil.copyfile(ROOT / "edgar_warehouse/control_contract.py", package / "control_contract.py")
    shutil.copytree(ROOT / "edgar_warehouse/change_journal", package / "change_journal",
                    ignore=shutil.ignore_patterns("__pycache__"))
    return tmp_path


def run_isolated(root, code, *, arguments=(), environment=None, python=None, installed=False):
    env = {**os.environ, **(environment or {}), "PYTHONPATH": str(root)}
    invocation = [python or sys.executable, *(["-I"] if installed else [])]
    return subprocess.run([*invocation, "-c", BOOTSTRAP + "\n" + code, *arguments],
                          cwd=root, env=env, text=True, capture_output=True, check=False,
                          timeout=60)
