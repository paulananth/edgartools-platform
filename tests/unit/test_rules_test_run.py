"""`rules test` reads each duty's login from the local stores' env files (ticket 14)."""
import pytest

from edgar_warehouse.rules import test_run


def write(folder, **files):
    for duty in test_run.DUTIES:
        (folder / f"{duty}.env").write_text(files.get(duty, ""))


def test_a_key_the_file_unsets_is_removed_from_the_duty_process(tmp_path, monkeypatch):
    write(tmp_path, worker="unset OTHER_DATABASE_URL MDM_DATABASE_URL\nexport MDM_DATABASE_URL='postgresql://w@h/mdm'\n")
    monkeypatch.setenv("OTHER_DATABASE_URL", "postgresql://shell@elsewhere/db")

    found = test_run.duties(tmp_path)

    assert found["worker"] == {"OTHER_DATABASE_URL": None, "MDM_DATABASE_URL": "postgresql://w@h/mdm"}
    seen = {}
    monkeypatch.setattr(test_run.subprocess, "run", lambda command, env, **_: seen.update(env) or
                        type("Done", (), {"returncode": 0, "stdout": "{}", "stderr": ""})())
    test_run._Commands(found, "file:///reports")("worker", "bookkeeping", "status", "1")
    assert "OTHER_DATABASE_URL" not in seen
    assert seen["MDM_DATABASE_URL"] == "postgresql://w@h/mdm"


def test_a_missing_duty_file_names_the_command_that_makes_it(tmp_path):
    (tmp_path / "worker.env").write_text("")

    with pytest.raises(test_run.TestRunError, match="local-test-stores.py up"):
        test_run.duties(tmp_path)


def test_a_source_without_a_mastering_target_is_refused(tmp_path, monkeypatch):
    write(tmp_path)
    monkeypatch.setattr(test_run.files, "source", lambda name: {"source": name})

    with pytest.raises(test_run.TestRunError, match="declares no `mastering` target"):
        test_run.run(source="example", capture=tmp_path, documents=tmp_path / "d.json", capture_run="r",
                     as_of="2026-10-18T00:00:00Z", stores=tmp_path, out=tmp_path / "out.json")
