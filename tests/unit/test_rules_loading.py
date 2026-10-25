"""`edgar-warehouse load`: any source's target over a capture, in bundles (ticket 136).

Every name below is invented: the command knows no source or store by name."""
import json
import threading
import time

import pytest

from edgar_warehouse.rules import driving, loading

READING = {
    "execution": {"max_artifacts": 2},
    "bookkeeping": {"targets": {
        "by_letter": {"steps": [{"name": "read", "operation": "source.read", "input": {"files": "letters/*"}},
                                {"name": "merge", "operation": "mdm.merge"}]},
        "everything": {"steps": [{"name": "read", "operation": "source.read", "input": {}}]},
    }},
}


def capture(folder, *keys):
    folder.mkdir(exist_ok=True)
    (folder / "receipts.jsonl").write_text("".join(json.dumps({"file": k, "sha256": "0" * 64}) + "\n" for k in keys))
    return folder


def test_the_documents_are_the_receipts_the_first_step_reads(tmp_path):
    folder = capture(tmp_path / "c", "letters/b.json", "numbers/1.json", "letters/a.json")

    assert loading.documents(READING, "by_letter", folder) == ["letters/a.json", "letters/b.json"]
    assert loading.documents(READING, "everything", folder) == ["letters/a.json", "letters/b.json", "numbers/1.json"]


def test_bundles_hold_at_most_the_sources_limit_in_key_order():
    assert loading.bundles(["a", "b", "c", "d", "e"], 2) == [["a", "b"], ["c", "d"], ["e"]]
    with pytest.raises(driving.RunStopped):
        loading.bundles(["a"], 0)


class Recorded:
    """The platform's commands, answered from invented state, and every call kept."""

    def __init__(self, open_runs=(), processed=(), versions=None, pinned=None):
        self.calls, self.open, self.processed, self.submitted = [], list(open_runs), set(processed), 0
        self.versions, self.pinned = versions or {}, pinned or {}

    def __call__(self, duty, *args):
        self.calls.append(args[:2])
        if args[:2] == ("workers", "describe"):
            return json.dumps({"profile": args[2], "runtime": "this-checkout"})
        if args[:2] == ("rules", "status"):
            return json.dumps([{"version": "example-2", "status": "active"}, {"version": "example-1", "status": "retired"}])
        if args[:2] == ("bookkeeping", "runs"):
            state = args[args.index("--state") + 1]
            return json.dumps([{"run_id": r, "name": n, "target": t, "created_at": r}
                               for r, n, t, s in self.open if s == state])
        if args[:2] == ("mdm", "prepare-capture"):
            bundle = json.loads(open(args[args.index("--documents") + 1]).read())
            fresh = [k for k in bundle if k not in self.processed]
            return json.dumps({"scope": {"documents": len(fresh)},
                               "manifest": {"uri": "file:///m", "sha256": "1" * 64} if fresh else None})
        if args[:2] == ("rules", "run"):
            self.submitted += 1
            return json.dumps({"run": {"run_id": f"new-{self.submitted}"}})
        raise AssertionError(args)

    def status(self, run_id):
        return {"run": {"submission": {"rules": {"uri": f"file:///frozen/{run_id}", "sha256": "2" * 64},
                                       "rule_version": self.versions.get(run_id, "example-2")},
                        "runtimes": self.pinned.get(run_id, {"source.read": "this-checkout",
                                                             "verify:source.read": "this-checkout"})}}

    def drive(self, run_id, steps):
        self.calls.append(("drive", run_id, tuple(step["name"] for step in steps)))
        return {"run": {"state": "complete"}, "counts": {"verified": 2}}


def loader(tmp_path, monkeypatch, commands, at_a_time=1):
    for duty in driving.DUTIES:
        (tmp_path / f"{duty}.env").write_text("export BOOKKEEPING_MANIFEST_ROOT=file://%s/m\n" % tmp_path)
    monkeypatch.setattr(loading.files, "source", lambda name: READING)
    # Each run's frozen rules: an older version, whose target had one step only.
    frozen = {"body": {"bookkeeping": {"targets": {"by_letter": {"steps": [{"name": "read"}]}}}}}
    monkeypatch.setattr(loading, "Artifacts", lambda: type("Frozen", (), {"json": lambda self, ref: frozen})())
    found = loading.Loader(source="example", target="by_letter", stores=tmp_path, workers=2, minutes=1,
                           at_a_time=at_a_time, say=lambda line: None)
    found.commands = commands
    return found


def test_each_new_bundle_is_prepared_submitted_and_driven(tmp_path, monkeypatch):
    commands = Recorded(processed={"letters/a.json", "letters/b.json"})
    folder = capture(tmp_path / "c", "letters/a.json", "letters/b.json", "letters/c.json")

    result = loader(tmp_path, monkeypatch, commands).load(
        capture=folder, capture_run="capture-1", as_of="2026-10-25T00:00:00Z", facts=[], run_files=[])

    assert [(b["documents"], b["new"], b["run_id"]) for b in result["bundles"]] == [(2, 0, None), (1, 1, "new-1")]
    assert ("drive", "new-1", ("read",)) in commands.calls  # the run's frozen steps, not the files on disk
    assert (tmp_path / "m" / "load" / "example" / "by_letter" / "2026-10-25T000000Z" / "bundle-002").is_dir()


def test_a_run_left_open_is_finished_before_anything_new(tmp_path, monkeypatch):
    commands = Recorded(open_runs=[("old-1", "example", "by_letter", "waiting"),
                                   ("other-1", "example", "everything", "running")],
                        processed={"letters/a.json"})
    folder = capture(tmp_path / "c", "letters/a.json")

    result = loader(tmp_path, monkeypatch, commands).load(
        capture=folder, capture_run="capture-1", as_of="2026-10-25T00:00:00Z", facts=[], run_files=[])

    assert result["finished_open_runs"] == ["old-1"]
    assert commands.calls.index(("drive", "old-1", ("read",))) < commands.calls.index(("mdm", "prepare-capture"))
    assert not [c for c in commands.calls if c[:2] == ("drive", "other-1")]


def test_a_blocked_run_stops_the_load_before_anything_is_submitted(tmp_path, monkeypatch):
    commands = Recorded(open_runs=[("stuck-1", "example", "by_letter", "blocked")])
    folder = capture(tmp_path / "c", "letters/a.json")

    with pytest.raises(driving.RunStopped, match="Run stuck-1 of example by_letter is blocked"):
        loader(tmp_path, monkeypatch, commands).load(
            capture=folder, capture_run="capture-1", as_of="2026-10-25T00:00:00Z", facts=[], run_files=[])
    assert ("mdm", "prepare-capture") not in commands.calls


def test_a_blocked_run_under_retired_rules_stays_as_it_is_and_the_load_goes_on(tmp_path, monkeypatch):
    commands = Recorded(open_runs=[("old-rules-1", "example", "by_letter", "blocked")],
                        versions={"old-rules-1": "example-1"})
    folder = capture(tmp_path / "c", "letters/a.json")

    result = loader(tmp_path, monkeypatch, commands).load(
        capture=folder, capture_run="capture-1", as_of="2026-10-25T00:00:00Z", facts=[], run_files=[])

    assert result["left_as_they_are"] == {"old-rules-1": "blocked under retired rules version example-1"}
    assert not [c for c in commands.calls if c[:2] == ("drive", "old-rules-1")]
    assert [b["run_id"] for b in result["bundles"]] == ["new-1"]


def test_a_target_the_source_does_not_declare_is_refused(monkeypatch):
    monkeypatch.setattr(loading.files, "source", lambda name: READING)

    with pytest.raises(driving.RunStopped, match="declares no `missing` target"):
        loading.target_of("example", "missing")


def test_an_open_run_pinned_to_other_worker_code_is_left_and_its_documents_load_anew(tmp_path, monkeypatch):
    commands = Recorded(open_runs=[("other-code-1", "example", "by_letter", "running")],
                        pinned={"other-code-1": {"source.read": "this-checkout", "source.combine": "older-code",
                                                 "verify:source.combine": "older-code"}})
    folder = capture(tmp_path / "c", "letters/a.json")

    result = loader(tmp_path, monkeypatch, commands).load(
        capture=folder, capture_run="capture-1", as_of="2026-10-25T00:00:00Z", facts=[], run_files=[])

    assert result["left_as_they_are"] == {"other-code-1": "pinned to other worker code (source.combine)"}
    assert result["finished_open_runs"] == []
    assert [b["run_id"] for b in result["bundles"]] == ["new-1"]


class Overlapping(Recorded):
    """Each run takes a moment to drive; counts how many were driven at the same time."""

    def __init__(self, stop=None, **kwargs):
        super().__init__(**kwargs)
        self.lock, self.now, self.most, self.stop = threading.Lock(), 0, 0, stop

    def __call__(self, duty, *args):
        if args[:2] == ("rules", "run"):
            bundle = args[args.index("--input-manifest") + 1]
            with self.lock:
                self.submitted += 1
            return json.dumps({"run": {"run_id": f"run-for-{bundle}"}})
        if args[:2] == ("mdm", "prepare-capture"):
            where = args[args.index("--output") + 1]
            return json.dumps({"scope": {"documents": 2}, "manifest": {"uri": where, "sha256": "1" * 64}})
        return super().__call__(duty, *args)

    def drive(self, run_id, steps):
        with self.lock:
            self.now += 1
            self.most = max(self.most, self.now)
        time.sleep(0.05)
        with self.lock:
            self.now -= 1
        if self.stop and self.stop in run_id:
            raise driving.RunStopped(f"step read: unit x failed in {run_id}")
        return {"run": {"state": "complete"}, "counts": {"verified": 2}}


def test_bundles_of_one_target_load_at_once_and_report_in_order(tmp_path, monkeypatch):
    commands = Overlapping()
    folder = capture(tmp_path / "c", *(f"letters/{n}.json" for n in range(6)))

    result = loader(tmp_path, monkeypatch, commands, at_a_time=3).load(
        capture=folder, capture_run="capture-1", as_of="2026-10-25T00:00:00Z", facts=[], run_files=[])

    assert commands.most == 3
    assert [b["bundle"] for b in result["bundles"]] == [1, 2, 3]
    assert all(b["run_id"].endswith(f"bundle-00{b['bundle']}/manifest") for b in result["bundles"])


def test_a_bundle_that_stops_does_not_stop_the_others_and_is_named(tmp_path, monkeypatch):
    commands = Overlapping(stop="bundle-002")
    folder = capture(tmp_path / "c", *(f"letters/{n}.json" for n in range(6)))

    with pytest.raises(driving.RunStopped, match=r"1 of 3 stopped: step read: unit x failed in run-for-.*bundle-002"):
        loader(tmp_path, monkeypatch, commands, at_a_time=3).load(
            capture=folder, capture_run="capture-1", as_of="2026-10-25T00:00:00Z", facts=[], run_files=[])
    assert commands.submitted == 3


def test_at_least_one_bundle_at_a_time(tmp_path, monkeypatch):
    with pytest.raises(driving.RunStopped, match="At least one bundle"):
        loader(tmp_path, monkeypatch, Recorded(), at_a_time=0)
