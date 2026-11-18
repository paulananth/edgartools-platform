"""A load pays in memory for every library it imports, in every worker: a library only some sources need is imported
when one of them reads, not when the worker starts. Everything here is invented."""

import subprocess
import sys
from pathlib import Path


def _loaded(code: str) -> str:
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout.strip()


def test_a_load_that_reads_no_parquet_file_never_imports_pyarrow_or_numpy():
    loaded = _loaded("import sys, edgar_warehouse.rules.loading, edgar_warehouse.workers.source_read;"
                     "print('pyarrow' in sys.modules, 'numpy' in sys.modules)")
    assert loaded == "False False"


def test_the_parquet_files_a_run_pins_are_the_same_without_importing_pyarrow():
    """They feed the processing identity: naming them lazily must not change a digest."""
    named = _loaded("import sys; from edgar_warehouse.workers import source_parquet;"
                    "print(*source_parquet.runtime_files(), 'pyarrow' in sys.modules, sep='|')").split("|")
    import pyarrow._parquet as codec
    import pyarrow.parquet as pq

    assert named[:2] == [str(Path(pq.__file__)), str(Path(codec.__file__))]
    assert named[2] == "False"


def test_a_pyarrow_without_a_compiled_reader_fails_with_a_named_error_not_a_stop_iteration(tmp_path, monkeypatch):
    import importlib.util
    import types

    import pytest

    from edgar_warehouse.workers import source_parquet

    package = tmp_path / "pyarrow"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "_parquet.pyx").write_text("")  # the source of the reader is there; the compiled reader is not
    monkeypatch.setattr(source_parquet, "find_spec", lambda name: types.SimpleNamespace(origin=str(package / "__init__.py")))
    with pytest.raises(ImportError, match="no compiled Parquet reader"):
        source_parquet.runtime_files()
    monkeypatch.setattr(source_parquet, "find_spec", lambda name: None)
    with pytest.raises(ImportError, match="pyarrow is not installed"):
        source_parquet.runtime_files()
    assert importlib.util.find_spec("pyarrow") is not None  # the real one is untouched
