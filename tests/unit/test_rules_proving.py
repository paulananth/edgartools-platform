"""`rules test` refuses a source or target it cannot run (ticket 14)."""
import pytest

from edgar_warehouse.rules import proving


def write(folder, **files):
    for duty in ("worker", "verifier", "governance"):
        (folder / f"{duty}.env").write_text(files.get(duty, ""))


def test_a_source_without_a_mastering_target_is_refused(tmp_path, monkeypatch):
    write(tmp_path)
    monkeypatch.setattr(proving.files, "source", lambda name: {"source": name})

    with pytest.raises(proving.TestRunError, match="declares no `mastering` target"):
        proving.run(source="example", capture=tmp_path, documents=tmp_path / "d.json", capture_run="r",
                     as_of="2026-10-18T00:00:00Z", stores=tmp_path, out=tmp_path / "out.json")


def test_the_named_target_is_the_one_tested(tmp_path, monkeypatch):
    write(tmp_path)
    monkeypatch.setattr(proving.files, "source", lambda name: {
        "source": name, "bookkeeping": {"version": 2, "targets": {"mastering": {"steps": []}}}})

    with pytest.raises(proving.TestRunError, match="declares no `mastering_isin` target"):
        proving.run(source="example", capture=tmp_path, documents=tmp_path / "d.json", capture_run="r",
                     as_of="2026-10-18T00:00:00Z", stores=tmp_path, out=tmp_path / "out.json", target="mastering_isin")
