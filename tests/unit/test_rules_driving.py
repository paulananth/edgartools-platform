"""The run driver `rules test` and `load` share (ticket 136)."""
import json

import pytest

from edgar_warehouse.bookkeeping.clean.engine import CONTENTION
from edgar_warehouse.rules import driving


def write(folder, **files):
    for duty in driving.DUTIES:
        (folder / f"{duty}.env").write_text(files.get(duty, ""))


def commands(env, folder, **kwargs):
    return driving.Commands(env, "file:///reports", deadline=driving.time.monotonic() + 60,
                            log=folder / "errors.log", **kwargs)


class Script(driving.Commands):
    """Answers each command from a list of status pages, one per pass, and records the calls."""

    def __init__(self, pages, *, workers=1, deadline=60):
        super().__init__({}, "file:///reports", deadline=driving.time.monotonic() + deadline,
                         log=driving.Path("unused"), workers=workers)
        self.pages, self.calls = list(pages), []

    def __call__(self, duty, *args):
        self.calls.append((duty, *args[:3]))
        if args[:2] == ("bookkeeping", "status"):
            step = args[args.index("--step") + 1]
            page = [i for i in (self.pages.pop(0) if len(self.pages) > 1 else self.pages[0]) if i["step"] == step]
            counts = {}
            for item in page:
                counts[item["state"]] = counts.get(item["state"], 0) + 1
            return json.dumps({"items": page, "counts": counts})
        if args[:2] == ("bookkeeping", "finalize"):
            return json.dumps({"run": {"state": "complete"}})
        return ""


def unit(step, state, error=None, key="k"):
    return {"step": step, "state": state, "error": error, "unit_key": key}


STEPS = [{"name": "read", "operation": "source.read"}, {"name": "merge", "operation": "mdm.merge"}]


def test_steps_run_in_declared_order_with_workers_only_where_units_are_left(monkeypatch):
    monkeypatch.setattr(driving.time, "sleep", lambda _: None)
    read = [unit("read", "pending", key=k) for k in "abc"]
    script = Script([read, [{**u, "state": "verified"} for u in read],
                     [unit("merge", "pending")], [unit("merge", "verified")]], workers=3)

    assert script.drive("run-1", STEPS) == {"run": {"state": "complete"}}

    work = [c for c in script.calls if c[1:3] == ("workers", "work")]
    verify = [c for c in script.calls if c[1:3] == ("workers", "verify")]
    assert [c[3] for c in work] == ["source.read"] * 3 + ["mdm.merge"]  # one worker for a one-unit step
    assert [c[0] for c in verify] == ["verifier", "verifier"]
    assert script.calls[-1] == ("worker", "bookkeeping", "finalize", "run-1")


def test_a_step_already_verified_starts_no_worker():
    script = Script([[unit("read", "verified")]], workers=3)

    script.drive("run-1", STEPS[:1])

    assert not [c for c in script.calls if c[1] == "workers"]


def test_a_unit_waiting_on_busy_prerequisites_is_tried_again(monkeypatch):
    monkeypatch.setattr(driving.time, "sleep", lambda _: None)
    script = Script([[unit("read", "waiting", CONTENTION)], [unit("read", "waiting", CONTENTION)],
                     [unit("read", "verified")]])

    assert script.drive("run-1", STEPS[:1])["run"]["state"] == "complete"
    assert len([c for c in script.calls if c[1:3] == ("workers", "work")]) == 2


def test_a_pass_that_moved_nothing_pauses_before_the_next(monkeypatch):
    paused = []
    monkeypatch.setattr(driving.time, "sleep", paused.append)
    script = Script([[unit("read", "running")], [unit("read", "running")], [unit("read", "verified")]])

    script.drive("run-1", STEPS[:1])

    assert paused == [driving.PAUSE]


def test_a_unit_that_failed_stops_the_run_and_says_how_to_go_on(monkeypatch):
    monkeypatch.setattr(driving.time, "sleep", lambda _: None)
    script = Script([[unit("read", "pending", key="answers-16")],
                     [unit("read", "waiting", "ValueError", key="answers-16")]])

    with pytest.raises(driving.RunStopped, match="unit answers-16 failed .ValueError.; see bookkeeping status run-1 "
                                                 "--step read, fix it, then drive run run-1 again"):
        script.drive("run-1", STEPS[:1])


def test_a_unit_that_failed_before_is_tried_again_first(monkeypatch):
    monkeypatch.setattr(driving.time, "sleep", lambda _: None)
    script = Script([[unit("read", "waiting", "ValueError")], [unit("read", "verified")]])

    assert script.drive("run-1", STEPS[:1])["run"]["state"] == "complete"


def test_the_deadline_stops_the_run_resumably():
    script = Script([[unit("read", "running")]], deadline=0)

    with pytest.raises(driving.RunStopped, match="did not finish before the deadline; drive run run-1 again"):
        script.drive("run-1", STEPS[:1])


def test_at_least_one_worker(tmp_path):
    with pytest.raises(driving.RunStopped, match="At least one worker"):
        commands({}, tmp_path, workers=0)


@pytest.mark.parametrize("value, folder", [
    ("file:///Users/a/manifests", "/Users/a/manifests"),
    ("file:///Users/a/my%20manifests", "/Users/a/my manifests"),
    ("/Users/a/manifests", "/Users/a/manifests"),
])
def test_the_manifest_root_is_a_local_folder(value, folder):
    assert driving.manifest_root({"worker": {"BOOKKEEPING_MANIFEST_ROOT": value}}) == driving.Path(folder)


@pytest.mark.parametrize("value", ["s3://bucket/manifests", ""])
def test_a_manifest_root_that_is_not_local_is_refused(value):
    with pytest.raises(driving.RunStopped, match="local folder"):
        driving.manifest_root({"worker": {"BOOKKEEPING_MANIFEST_ROOT": value}})


def test_a_failed_command_keeps_its_message_off_the_screen(tmp_path, monkeypatch):
    message = "connection to server at 127.0.0.1 port 5433 failed for user worker"
    monkeypatch.setattr(driving.subprocess, "run", lambda *_, **__:
                        type("Done", (), {"returncode": 1, "stdout": "", "stderr": message})())

    with pytest.raises(driving.RunStopped) as caught:
        commands({"worker": {}}, tmp_path)("worker", "workers", "work", "source.read", "1")

    assert "127.0.0.1" not in str(caught.value) and "status 1" in str(caught.value)
    assert message in (tmp_path / "errors.log").read_text()
    assert (tmp_path / "errors.log").stat().st_mode & 0o777 == 0o600


def test_a_key_the_file_unsets_is_removed_from_the_duty_process(tmp_path, monkeypatch):
    write(tmp_path, worker="unset OTHER_DATABASE_URL MDM_DATABASE_URL\nexport MDM_DATABASE_URL='postgresql://w@h/mdm'\n")
    monkeypatch.setenv("OTHER_DATABASE_URL", "postgresql://shell@elsewhere/db")

    found = driving.duties(tmp_path)

    assert found["worker"] == {"OTHER_DATABASE_URL": None, "MDM_DATABASE_URL": "postgresql://w@h/mdm"}
    seen = {}
    monkeypatch.setattr(driving.subprocess, "run", lambda command, env, **_: seen.update(env) or
                        type("Done", (), {"returncode": 0, "stdout": "{}", "stderr": ""})())
    commands(found, tmp_path)("worker", "bookkeeping", "status", "1")
    assert "OTHER_DATABASE_URL" not in seen
    assert seen["MDM_DATABASE_URL"] == "postgresql://w@h/mdm"


def test_a_missing_duty_file_names_the_command_that_makes_it(tmp_path):
    (tmp_path / "worker.env").write_text("")

    with pytest.raises(driving.RunStopped, match="local-test-stores.py up"):
        driving.duties(tmp_path)
