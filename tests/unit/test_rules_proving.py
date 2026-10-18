"""`rules test` reads each duty's login from the local stores' env files (ticket 14)."""
import pytest

from edgar_warehouse.rules import proving


def write(folder, **files):
    for duty in proving.DUTIES:
        (folder / f"{duty}.env").write_text(files.get(duty, ""))


def commands(env, folder):
    return proving._Commands(env, "file:///reports", deadline=proving.time.monotonic() + 60, log=folder / "errors.log")


def test_a_failed_command_keeps_its_message_off_the_screen(tmp_path, monkeypatch):
    message = "connection to server at 127.0.0.1 port 5433 failed for user worker"
    monkeypatch.setattr(proving.subprocess, "run", lambda *_, **__:
                        type("Done", (), {"returncode": 1, "stdout": "", "stderr": message})())

    with pytest.raises(proving.TestRunError) as caught:
        commands({"worker": {}}, tmp_path)("worker", "workers", "work", "source.read", "1")

    assert "127.0.0.1" not in str(caught.value) and "status 1" in str(caught.value)
    assert message in (tmp_path / "errors.log").read_text()
    assert (tmp_path / "errors.log").stat().st_mode & 0o777 == 0o600


def test_a_key_the_file_unsets_is_removed_from_the_duty_process(tmp_path, monkeypatch):
    write(tmp_path, worker="unset OTHER_DATABASE_URL MDM_DATABASE_URL\nexport MDM_DATABASE_URL='postgresql://w@h/mdm'\n")
    monkeypatch.setenv("OTHER_DATABASE_URL", "postgresql://shell@elsewhere/db")

    found = proving.duties(tmp_path)

    assert found["worker"] == {"OTHER_DATABASE_URL": None, "MDM_DATABASE_URL": "postgresql://w@h/mdm"}
    seen = {}
    monkeypatch.setattr(proving.subprocess, "run", lambda command, env, **_: seen.update(env) or
                        type("Done", (), {"returncode": 0, "stdout": "{}", "stderr": ""})())
    commands(found, tmp_path)("worker", "bookkeeping", "status", "1")
    assert "OTHER_DATABASE_URL" not in seen
    assert seen["MDM_DATABASE_URL"] == "postgresql://w@h/mdm"


def test_a_missing_duty_file_names_the_command_that_makes_it(tmp_path):
    (tmp_path / "worker.env").write_text("")

    with pytest.raises(proving.TestRunError, match="local-test-stores.py up"):
        proving.duties(tmp_path)


def test_a_source_without_a_mastering_target_is_refused(tmp_path, monkeypatch):
    write(tmp_path)
    monkeypatch.setattr(proving.files, "source", lambda name: {"source": name})

    with pytest.raises(proving.TestRunError, match="declares no `mastering` target"):
        proving.run(source="example", capture=tmp_path, documents=tmp_path / "d.json", capture_run="r",
                     as_of="2026-10-18T00:00:00Z", stores=tmp_path, out=tmp_path / "out.json")
