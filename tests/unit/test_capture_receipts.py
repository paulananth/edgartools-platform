"""The capture receipts tool writes one receipt per file and never replaces a capture's receipts."""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

PATH = Path(__file__).resolve().parents[2] / "skills/data-operations/scripts/capture_receipts.py"
spec = importlib.util.spec_from_file_location("capture_receipts", PATH)
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


def folder_with(tmp_path):
    (tmp_path / "pages").mkdir()
    (tmp_path / "pages" / "b.capture.zip").write_bytes(b"second")
    (tmp_path / "a.capture.zip").write_bytes(b"first")
    (tmp_path / "notes.txt").write_bytes(b"not a capture")
    return tmp_path


def test_each_matching_file_gets_one_receipt_by_its_path_with_the_sha256_of_its_bytes(tmp_path):
    folder = folder_with(tmp_path)

    assert tool.write(folder, "*.capture.zip") == 2

    lines = (folder / "receipts.jsonl").read_text().splitlines()
    assert [json.loads(line) for line in lines] == [
        {"file": "a.capture.zip", "sha256": hashlib.sha256(b"first").hexdigest()},
        {"file": "pages/b.capture.zip", "sha256": hashlib.sha256(b"second").hexdigest()}]


def test_receipts_already_written_are_never_replaced_and_the_captured_files_are_untouched(tmp_path):
    folder = folder_with(tmp_path)
    tool.write(folder, "*.capture.zip")
    before = (folder / "receipts.jsonl").read_bytes()

    with pytest.raises(SystemExit, match="never replaced"):
        tool.write(folder, "*.capture.zip")

    assert (folder / "receipts.jsonl").read_bytes() == before
    assert (folder / "a.capture.zip").read_bytes() == b"first"


def test_a_pattern_that_matches_nothing_writes_no_receipts_file(tmp_path):
    with pytest.raises(SystemExit, match="No file matches"):
        tool.write(folder_with(tmp_path), "*.nothing")
    assert not (tmp_path / "receipts.jsonl").exists()
