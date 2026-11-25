"""The load jobs names every target a store loads, each with the facts its target declares."""
import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest
import yaml

from edgar_warehouse.rules import files

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("load_jobs", ROOT / "skills/data-operations/scripts/load_jobs.py")
chain = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(chain)
STEPS = chain.load_jobs()
INFER = importlib.util.spec_from_file_location("infer_dependencies", ROOT / "skills/data-operations/scripts/infer_dependencies.py")
infer = importlib.util.module_from_spec(INFER)
INFER.loader.exec_module(infer)
INFERRED = infer.infer()
BY_NAME = {step["name"]: step for step in STEPS}


def targets():
    """Each (source, target) that loads a capture; a target that only copies or fetches one is not loaded here."""
    return {(name, target): body for name in sorted(p.parent.name for p in (files.sources_root()).glob("*/source.yaml"))
            for target, body in (files.source(name).get("bookkeeping", {}).get("targets") or {}).items()
            if not {step["operation"] for step in body["steps"]} & {"artifact.copy", "provider.capture"}}


def test_step_names_are_unique_and_each_names_a_target_that_loads():
    names = [step["name"] for step in STEPS]
    assert len(names) == len(set(names))
    assert {(s["source"], s["target"]) for s in STEPS} <= set(targets())


def test_every_target_that_loads_a_capture_is_in_the_chain():
    assert set(targets()) <= {(s["source"], s["target"]) for s in STEPS}


def test_a_later_delivery_of_one_source_carries_the_next_revision():
    seen = {}
    for step in STEPS:
        for one in chain.loads(step):
            if "revision" in one:
                seen.setdefault((step["source"], one["capture"].split("/")[0]), []).append((one["capture"], one["revision"]))
    for key, runs in seen.items():
        order = list(dict.fromkeys(runs))
        assert [r for _, r in order] == list(range(len(order))), key


def test_the_arguments_follow_the_step():
    step = {"name": "x", "source": "s", "target": "t", "capture": "a/b", "workers": 2, "bundles": 3, "minutes": 5,
            "revision": 1, "capture_run": "label-x", "facts": {"run": "label-x"}}
    args = chain.arguments(step)
    assert args[:4] == ["--source", "s", "--target", "t"]
    assert args[args.index("--capture-run") + 1] == "label-x"
    assert args[args.index("--revision") + 1] == "1"
    assert args[args.index("--fact") + 1] == "run=label-x"


def test_the_run_label_is_no_input_of_a_load(monkeypatch):
    """A fact is part of what a file is processed under: a run label in one made a rerun under another label process
    every company document again, and the Stage refused the changed records under the same revision."""
    monkeypatch.setattr(chain, "RUN", "one-label")
    first = [chain.arguments(one) for step in chain.load_jobs() for one in chain.loads(step)]
    monkeypatch.setattr(chain, "RUN", "another-label")
    assert [chain.arguments(one) for step in chain.load_jobs() for one in chain.loads(step)] == first
    company = BY_NAME["company"]
    assert company["capture_run"] == "fresh-v1-company"  # the label the store's records were loaded under
    assert company["facts"]["capture_run"] == "fresh-v1-company" and company["facts"]["catalog_run"] == "fresh-v1-catalog"


def test_an_env_file_is_read_as_data(tmp_path):
    path = tmp_path / "worker.env"
    path.write_text("unset OTHER\nexport ONE='a b'\nTWO=plain\nexport THREE=\n# a comment\n")
    assert chain.load_env(path) == {"ONE": "a b", "TWO": "plain", "THREE": ""}


def test_every_step_has_a_lane_and_waits_only_for_steps_that_exist():
    names = {step["name"] for step in STEPS}
    for step in STEPS:
        assert step["lane"], step["name"]
        assert set(step.get("waits_for") or []) <= names - {step["name"]}, step["name"]


def test_the_lanes_run_to_the_end_together_with_no_step_waiting_on_a_later_one():
    """Each lane takes its steps in file order and a step runs once what it waits for is done: no lane deadlocks."""
    assert chain.wait_problems(STEPS) == []

def test_the_chain_builds_the_links_table_once_after_the_loads_and_no_target_builds_it():
    builds = sorted(f"{s}/{t}" for (s, t), body in targets().items()
                    if any((x.get("input") or {}).get("keys", {}).get("build") == "links" for x in body["steps"]))
    assert builds == []
    assert all("--no-links" in chain.arguments(one) for step in STEPS for one in chain.loads(step))
    calls = []
    original = chain.run
    chain.run = lambda args, env, log=None: calls.append(args) or 0
    try:
        chain.finish({}, Path("/dev/null"))
    finally:
        chain.run = original
    assert calls == [["silver", "links"]]  # a silver row finds its master by a join: no master id is filled afterwards


def test_the_chain_has_eleven_lanes_and_company_facts_is_beside_the_other_silver_only_sources():
    """GLEIF and N-PORT silver each have a lane: neither waits for the Securities that came before in one lane."""
    assert {step["lane"] for step in STEPS} == set("APSCLODFGNQ")
    assert {s["lane"] for s in STEPS if s["source"] == "gleif"} == {"G"}
    assert {s["lane"] for s in STEPS if s["name"] == "nport-security-silver"} == {"N"}
    assert {s["lane"] for s in STEPS if s["name"].startswith("nport-security") and s["target"] != "silver"} == {"Q"}
    assert {s["lane"] for s in STEPS if s["source"] == "sec.company-facts"} == {"F"}


def test_no_step_asks_for_more_workers_than_the_largest_capacity_profile_carries():
    """A smaller profile clamps a step's workers at start (a medium task starts GLEIF at 4); none may exceed the largest."""
    largest = max(chain.workers_range(**profile)[1] for profile in chain.capacity_profiles().values())
    counts = {step["name"]: step["workers"] for step in STEPS}
    assert min(counts.values()) >= 1 and max(counts.values()) <= largest, (counts, largest)


def test_the_skill_names_eleven_lanes_and_the_capacity_profiles():
    skill = (ROOT / "skills/data-operations/SKILL.md").read_text()
    runbook = (ROOT / "docs/runbooks/edgar-intelligence/init.md").read_text()
    assert "A P S C L O D F G N Q" in skill and "A P S C L O D F G N Q" in runbook
    assert "capacity profile" in skill and "--capacity" in skill
    assert "from 2 to 8" not in skill and "scales to 8" not in skill


def test_a_step_waits_for_what_another_lane_has_done(tmp_path):
    state = tmp_path / "state.log"
    state.write_text("11-15 14:00:00 ET alpha done: x\n11-15 14:01:00 ET beta attempt 1 start\n")
    assert chain.done_steps(state) == {"alpha"}
    assert chain.done_steps(tmp_path / "none.log") == set()


def key(step):
    return f"{step['source']}/{step['target']}"


def ancestors(name):
    """Every step that must be done before this one: its lane's earlier steps and what each waits for."""
    before = {}
    last = {}
    for step in STEPS:
        before[step["name"]] = set(step.get("waits_for") or [])
        if step["lane"] in last:
            before[step["name"]].add(last[step["lane"]])
        last[step["lane"]] = step["name"]
    found, todo = set(), [name]
    while todo:
        for earlier in before[todo.pop()]:
            if earlier not in found:
                found.add(earlier)
                todo.append(earlier)
    return found


def steps_of(source):
    """The load jobs of one source that master (a target with a kind of its own)."""
    return [s["name"] for s in STEPS if s["source"] == source and INFERRED[key(s)]["kinds"]]


def test_a_load_follows_the_sources_its_rules_prefer():
    for step in STEPS:
        item = INFERRED[key(step)]
        wanted = set(item["prefer_after"])
        for source in wanted - {step["source"]}:
            assert set(steps_of(source)) <= ancestors(step["name"]), (step["name"], source)


def test_every_wait_is_explained_by_what_the_rules_declare():
    for step in STEPS:
        item = INFERRED[key(step)]
        for waited in step.get("waits_for") or []:
            other = BY_NAME[waited]
            assert other["source"] in item["prefer_after"], (step["name"], waited)


def test_a_step_takes_the_chains_defaults_for_what_it_does_not_say(tmp_path):
    path = tmp_path / "chain.yaml"
    path.write_text(yaml.safe_dump({"defaults": {"workers": 2, "bundles": 1}, "capture_label": "l", "steps": [
        {"name": "plain", "minutes": 60}, {"name": "sized", "minutes": 60, "workers": 8}]}))

    assert [(s["name"], s["workers"], s["bundles"]) for s in chain.load_jobs(path)] == [("plain", 2, 1), ("sized", 8, 1)]


def test_every_step_of_the_chain_has_its_sizes():
    assert all(type(step[size]) is int and step[size] >= 1 for step in STEPS for size in ("workers", "bundles", "attempts"))


@pytest.fixture(autouse=True)
def _no_database(monkeypatch):
    """No test reads a real database."""
    monkeypatch.setattr(chain, "database_load", lambda reader_url: None)


def _step(name, lane, minutes=60, waits=(), source=None, target="mastering"):
    return {"name": name, "lane": lane, "minutes": minutes, "waits_for": list(waits), "source": source or name,
            "target": target}


def test_a_lane_offers_only_its_next_step_and_only_once_its_waits_are_done():
    steps = [_step("a1", "A"), _step("a2", "A"), _step("b1", "B", waits=["a1"])]
    assert chain.ready(steps, done=set(), running=set(), failed=set(), free=5) == ["a1"]
    assert chain.ready(steps, done={"a1"}, running=set(), failed=set(), free=5) == ["a2", "b1"]
    assert chain.ready(steps, done={"a1"}, running={"a2"}, failed=set(), free=5) == ["b1"]  # a2 holds its lane


def test_the_longest_step_starts_first_and_free_slots_bound_how_many_start():
    steps = [_step("short", "A", minutes=10), _step("long", "B", minutes=400), _step("mid", "C", minutes=90)]
    assert chain.ready(steps, set(), set(), set(), free=2) == ["long", "mid"]
    assert chain.ready(steps, set(), set(), set(), free=0) == []


def test_two_loads_of_one_source_and_target_never_start_together():
    steps = [_step("x1", "A", source="one"), _step("x2", "B", source="one"), _step("y", "C", source="two")]
    assert chain.ready(steps, set(), running=set(), failed=set(), free=5) == ["x1", "y"]
    assert chain.ready(steps, set(), running={"x1"}, failed=set(), free=5) == ["y"]  # x2 waits for x1's source and target


def test_a_failed_step_blocks_its_lane_and_whatever_waits_for_it_but_nothing_else():
    steps = [_step("a1", "A"), _step("a2", "A"), _step("b1", "B", waits=["a1"]), _step("c1", "C")]
    assert chain.ready(steps, done=set(), running=set(), failed={"a1"}, free=5) == ["c1"]


def test_a_failure_blocks_everything_after_it_through_the_lane_and_the_waits():
    steps = [_step("a1", "A"), _step("a2", "A"), _step("a3", "A"), _step("b1", "B", waits=["a2"]),
             _step("b2", "B")]
    assert chain.ready(steps, done=set(), running=set(), failed={"a1"}, free=5) == []  # a2, a3, b1, b2 all follow a1
    assert chain.blocked(steps, failed={"a2"}) == {"a3", "b1", "b2"}


def test_a_load_already_running_outside_the_scheduler_keeps_its_source_and_target_busy():
    steps = [_step("x1", "A", source="one"), _step("y", "B", source="two")]
    assert chain.ready(steps, set(), running=set(), failed=set(), free=5, busy={("one", "mastering")}) == ["y"]


def test_swap_used_is_read_from_the_systems_report():
    swap = "total = 9216.00M  used = 5751.50M  free = 1416.50M  (encrypted)"
    assert chain.swap_fraction(swap) == 5751.5 / 9216
    assert chain.swap_fraction("not a reading") is None



class _Child:
    """A started step that has already ended with `code`."""

    def __init__(self, code):
        self.returncode = code

    def poll(self):
        return self.returncode


def _scheduler(monkeypatch, tmp_path, outcomes):
    """Run `auto` with each step ending as `outcomes` says (a step done writes the line the state file holds)."""
    state = tmp_path / "state.log"
    started = []

    def popen(command, **_):
        name = command[command.index("--only") + 1]
        started.append(name)
        if outcomes[name] == 0:
            with state.open("a") as handle:
                handle.write(f"11-18 07:00:00 ET {name} done: Done\n")
        return _Child(outcomes[name])

    monkeypatch.setattr(chain.subprocess, "Popen", popen)
    monkeypatch.setattr(chain, "external_loads", lambda: set())
    monkeypatch.setattr(chain, "machine_pressure", lambda relaxed=False: "ok")
    monkeypatch.setattr(chain.time, "sleep", lambda _: None)
    monkeypatch.setattr(chain, "note", lambda message, path: None)
    return state, started


def test_the_scheduler_starts_each_step_when_its_lane_is_free_and_ends_when_all_are_done(monkeypatch, tmp_path):
    steps = [_step("a1", "A"), _step("a2", "A"), _step("b1", "B", waits=["a1"])]
    state, started = _scheduler(monkeypatch, tmp_path, {"a1": 0, "a2": 0, "b1": 0})
    assert chain.auto(steps, state, slots=2) == 0
    assert started.index("a1") < started.index("a2") and started.index("a1") < started.index("b1")
    assert sorted(started) == ["a1", "a2", "b1"]


def test_the_scheduler_stops_on_a_cycle_of_waits_instead_of_sleeping_forever(monkeypatch, tmp_path):
    steps = [_step("a1", "A", waits=["b1"]), _step("a2", "A"), _step("b1", "B", waits=["a2"])]
    state, started = _scheduler(monkeypatch, tmp_path, {"a1": 0, "a2": 0, "b1": 0})
    assert chain.auto(steps, state, slots=2) == 1
    assert started == []


def test_the_loads_running_on_the_machine_are_read_from_their_command_lines(monkeypatch):
    listing = ("/x/.venv/bin/python edgar-warehouse load --source one --target mastering --capture /c\n"
               "/bin/sh something else\n"
               "uv run edgar-warehouse load --source two --target silver --workers 2\n")
    monkeypatch.setattr(chain.subprocess, "run", lambda *a, **k: type("R", (), {"stdout": listing})())
    assert chain.external_loads() == {("one", "mastering"), ("two", "silver")}


def test_the_scheduler_carries_on_past_a_failed_step_and_stops_when_only_blocked_steps_remain(monkeypatch, tmp_path):
    steps = [_step("a1", "A"), _step("a2", "A"), _step("c1", "C")]
    state, started = _scheduler(monkeypatch, tmp_path, {"a1": 1, "a2": 0, "c1": 0})
    assert chain.auto(steps, state, slots=2) == 1
    assert sorted(started) == ["a1", "c1"]  # a2 follows the failed a1 and never starts


def test_a_short_step_that_gates_a_long_tail_starts_before_a_longer_step_that_gates_nothing():
    steps = [_step("gate", "A", minutes=10), _step("tail", "B", minutes=300, waits=["gate"]),
             _step("alone", "C", minutes=120)]
    assert chain.chain_length(steps) == {"gate": 310, "tail": 300, "alone": 120}
    assert chain.ready(steps, set(), set(), set(), free=1) == ["gate"]


def test_a_failure_with_low_headroom_does_not_stop_the_scheduler_while_a_step_can_still_start(monkeypatch, tmp_path):
    steps = [_step("a1", "A"), _step("a2", "A"), _step("c1", "C")]
    state, started = _scheduler(monkeypatch, tmp_path, {"a1": 1, "a2": 0, "c1": 0})
    readings = iter(["ok", "high", "high", "ok", "ok", "ok", "ok", "ok", "ok"])
    monkeypatch.setattr(chain, "machine_pressure", lambda relaxed=False: next(readings))
    assert chain.auto(steps, state, slots=2) == 1
    assert "c1" in started  # the machine was too busy for two cycles, and the chain waited rather than stopping


def test_compute_pressure_is_low_ok_or_high_and_relaxes_when_the_run_is_behind():
    assert chain.pressure(load=3.0, cores=8, swap_used=0.2) == "low"
    assert chain.pressure(load=7.0, cores=8, swap_used=0.2) == "ok"
    assert chain.pressure(load=13.0, cores=8, swap_used=0.2) == "high"  # over 1.5 x the cores
    assert chain.pressure(load=2.0, cores=8, swap_used=0.8) == "high"  # swap over 75%
    assert chain.pressure(load=13.0, cores=8, swap_used=0.8, relaxed=True) == "ok"  # behind: up to 2 x cores, 90% swap
    assert chain.pressure(load=17.0, cores=8, swap_used=0.2, relaxed=True) == "high"


EVERY = {name: (2, 8) for name in ("long", "mid", "short")}


def test_workers_double_on_the_longest_chain_first_and_halve_on_the_shortest_within_the_profiles_range():
    priority = {"long": 900, "mid": 300, "short": 50}
    assert chain.rescale({"long": 2, "mid": 2, "short": 2}, priority, "low", EVERY) == ("long", 4)
    assert chain.rescale({"long": 8, "mid": 2, "short": 2}, priority, "low", EVERY) == ("mid", 4)
    assert chain.rescale({"long": 8, "mid": 8, "short": 8}, priority, "low", EVERY) is None  # the ceiling is the profile's
    assert chain.rescale({"long": 8, "mid": 4, "short": 4}, priority, "high", EVERY) == ("short", 2)
    assert chain.rescale({"long": 2, "mid": 2, "short": 2}, priority, "high", EVERY) is None  # the floor is the profile's
    assert chain.rescale({"long": 4, "mid": 4, "short": 4}, priority, "ok", EVERY) is None


def test_a_run_is_behind_when_more_of_the_window_is_used_than_of_the_work_done():
    assert not chain.behind(elapsed=30, window=120, done=300, total=1000)  # 25% of the time, 30% of the work
    assert not chain.behind(elapsed=36, window=120, done=200, total=1000)  # 30% against 20%: within a tenth
    assert chain.behind(elapsed=60, window=120, done=200, total=1000)  # half the time, a fifth of the work


class _Live(_Child):
    """A started step that keeps running until it is told to stop."""

    def __init__(self, command):
        super().__init__(None)
        self.pid, self.command = id(self) % 90000 + 1000, command

    def wait(self, timeout=None):
        self.returncode = -15


class _Ended(Exception):
    """The test's own end for a run whose children never finish."""


def _timed(monkeypatch, tmp_path, steps, ticks, cycles=40):
    """`auto` with children that never end by themselves and a clock that moves `ticks` minutes a cycle, for `cycles` cycles."""
    state = tmp_path / "state.log"
    started, killed = [], []
    now = {"t": chain.datetime(2026, 11, 18, 8, 0, tzinfo=chain.ZoneInfo("America/New_York"))}
    cycle = {"n": 0}

    def popen(command, **_):
        child = _Live(command)
        started.append((command[command.index("--only") + 1], int(command[command.index("--workers") + 1])))
        return child

    def sleep(_):
        now["t"] += chain.timedelta(minutes=ticks)
        cycle["n"] += 1
        if cycle["n"] > cycles:
            raise _Ended()

    monkeypatch.setattr(chain.subprocess, "Popen", popen)
    monkeypatch.setattr(chain.os, "killpg", lambda pid, sig: killed.append(pid))
    monkeypatch.setattr(chain, "external_loads", lambda: set())
    monkeypatch.setattr(chain, "clock", lambda: now["t"])
    monkeypatch.setattr(chain.time, "sleep", sleep)
    monkeypatch.setattr(chain, "note", lambda message, path: None)
    return state, started, killed, now


def _run_auto(*args, **kwargs):
    """`auto` until the test's cycles end."""
    try:
        return chain.auto(*args, **kwargs)
    except _Ended:
        return None


def test_a_deadline_is_reported_as_missed_once_and_never_stops_a_load(monkeypatch, tmp_path):
    """Operator, 2026-11-18, after a deadline stopped four running steps that had hours of work in them: "Deadline must not
    stop loading". The deadline holds the run to its schedule and reports the miss; the loads go on."""
    steps = [_step("a1", "A", minutes=600), _step("b1", "B", minutes=600)]
    state, started, killed, now = _timed(monkeypatch, tmp_path, steps, ticks=30, cycles=12)
    monkeypatch.setattr(chain, "machine_pressure", lambda relaxed=False: "ok")
    notes = []
    monkeypatch.setattr(chain, "note", lambda message, path: notes.append(message))
    assert _run_auto(steps, state, slots=2, deadline=now["t"] + chain.timedelta(minutes=90)) is None  # still going: the test ended it
    assert killed == [] and [name for name, _ in started] == ["a1", "b1"]  # nothing was stopped, six hours on
    missed = [m for m in notes if "deadline" in m and "passed" in m]
    assert len(missed) == 1 and "still loading" in missed[0] and "a1" in missed[0]  # said once, naming what is left


def test_a_run_that_finishes_after_its_deadline_says_by_how_much(monkeypatch, tmp_path):
    steps = [_step("a1", "A", minutes=60)]
    state, started, killed, now = _timed(monkeypatch, tmp_path, steps, ticks=30, cycles=12)
    monkeypatch.setattr(chain, "machine_pressure", lambda relaxed=False: "ok")
    notes = []
    monkeypatch.setattr(chain, "note", lambda message, path: notes.append(message))
    deadline = now["t"] + chain.timedelta(minutes=90)
    finished_at = deadline + chain.timedelta(minutes=60)  # a multiple of the 30-minute cycle
    monkeypatch.setattr(chain, "done_steps", lambda path: {"a1"} if now["t"] >= finished_at else set())
    assert _run_auto(steps, state, slots=2, deadline=deadline) == 0
    assert any("60 min after the deadline" in m for m in notes) and killed == []


def test_a_run_that_finishes_in_the_first_cycle_past_its_deadline_still_says_so(monkeypatch, tmp_path):
    steps = [_step("a1", "A", minutes=60)]
    state, started, killed, now = _timed(monkeypatch, tmp_path, steps, ticks=30, cycles=12)
    monkeypatch.setattr(chain, "machine_pressure", lambda relaxed=False: "ok")
    notes = []
    monkeypatch.setattr(chain, "note", lambda message, path: notes.append(message))
    deadline = now["t"] + chain.timedelta(minutes=30)
    monkeypatch.setattr(chain, "done_steps", lambda path: {"a1"} if now["t"] > deadline else set())  # done the cycle the deadline passes
    assert _run_auto(steps, state, slots=2, deadline=deadline) == 0
    assert any("after the deadline" in m for m in notes)


def test_a_window_that_has_run_out_or_never_was_is_behind():
    assert chain.behind(elapsed=7200, window=-3600, done=0, total=100)  # the deadline had passed at launch
    assert chain.behind(elapsed=7200, window=0, done=100, total=100)
    assert not chain.behind(elapsed=0, window=3600, done=0, total=100)


def _paced(monkeypatch, started, now, per_worker=None, flat=None, total=149):
    """Each step's log as its bundles complete: a minute's rate from its latest worker count (`per_worker` for each worker) or a flat
    rate, counted from its latest start (an attempt's own bundles, as a real log shows them)."""
    mark = {"len": 0, "at": now["t"]}

    def text(name):
        if len(started) != mark["len"]:
            mark.update(len=len(started), at=now["t"])
        minutes = (now["t"] - mark["at"]).total_seconds() / 60
        rate = flat if flat is not None else per_worker * started[-1][1]
        done = int(minutes * rate)
        lines = [f"x silver: {total} documents in {total} bundles"]
        for i in range(1, done + 1):
            lines += [f"Bundle {i}/{total}: 512 of 512 documents to load", f"  run b{i} complete in 1.0 min"]
        lines.append(f"Bundle {done + 1}/{total}: 512 of 512 documents to load")
        return "\n".join(lines) + "\n"
    monkeypatch.setattr(chain, "step_log_text", text)


def test_a_running_step_is_restarted_with_more_workers_when_the_machine_has_room_and_each_raise_pays(monkeypatch, tmp_path):
    steps = [_step("a1", "A", minutes=600)]
    steps[0]["workers"] = 2
    state, started, killed, now = _timed(monkeypatch, tmp_path, steps, ticks=5, cycles=40)
    _paced(monkeypatch, started, now, per_worker=0.1)  # the rate doubles with the workers: every raise pays
    monkeypatch.setattr(chain, "machine_pressure", lambda relaxed=False: "low")
    _run_auto(steps, state, slots=2)
    assert [workers for _, workers in started][:3] == [2, 4, 8]  # doubled while there was room, stopping at 8
    assert len(killed) >= 2


def test_a_step_is_not_raised_again_when_the_last_raise_did_not_raise_its_rate(monkeypatch, tmp_path):
    """The restart is waste if the extra workers wait on the same bottleneck."""
    steps = [_step("a1", "A", minutes=600)]
    steps[0]["workers"] = 2
    state, started, killed, now = _timed(monkeypatch, tmp_path, steps, ticks=5, cycles=60)
    _paced(monkeypatch, started, now, flat=0.2)  # the same bundles a minute at any count
    monkeypatch.setattr(chain, "machine_pressure", lambda relaxed=False: "low")
    _run_auto(steps, state, slots=2)
    assert [workers for _, workers in started] == [2, 4]  # one try; it gained nothing, so it is held at 4


def test_a_short_spike_of_pressure_sheds_nothing_and_lasting_pressure_does(monkeypatch, tmp_path):
    steps = [_step("a1", "A", minutes=600)]
    steps[0]["workers"] = 8
    state, started, killed, now = _timed(monkeypatch, tmp_path, steps, ticks=2, cycles=12)
    _paced(monkeypatch, started, now, per_worker=0.05)
    spike = iter(["ok", "high", "high", "ok"] + ["ok"] * 20)
    monkeypatch.setattr(chain, "machine_pressure", lambda relaxed=False: next(spike, "ok"))
    _run_auto(steps, state, slots=2)
    assert [workers for _, workers in started] == [8]  # two pressed cycles are a spike, not a reason to restart
    steps2 = [_step("a1", "A", minutes=600)]
    steps2[0]["workers"] = 8
    state2, started2, killed2, now2 = _timed(monkeypatch, tmp_path, steps2, ticks=2, cycles=12)
    _paced(monkeypatch, started2, now2, per_worker=0.05)
    pressed = iter(["ok"] + ["high"] * 30)  # it starts at `ok` (nothing starts while pressed), then the pressure lasts
    monkeypatch.setattr(chain, "machine_pressure", lambda relaxed=False: next(pressed, "high"))
    _run_auto(steps2, state2, slots=2)
    assert started2[1] == ("a1", 4)  # pressure that lasted sheds


@pytest.mark.parametrize("level, kwargs, reason", [
    ("low", {"left": 10.0, "abandoned": 0.0}, "too little left"),
    ("low", {"left": None, "abandoned": 0.0}, "too little left"),
    ("low", {"left": 300.0, "abandoned": 3.0}, "bundle is in flight"),
    ("high", {"left": 300.0, "abandoned": 0.0, "pressed": 1}, "has not lasted"),
])
def test_a_move_that_would_not_repay_its_restart_names_why(level, kwargs, reason):
    base = {"left": 300.0, "abandoned": 0.0, "pressed": 0, "rates": {}, "workers": 4}
    assert reason in chain.worth_moving(level, **{**base, **kwargs})
    assert chain.worth_moving("low", **base) is None  # plenty left, a bundle just completed, nothing measured against it
    assert chain.worth_moving("high", **{**base, "pressed": 4}) is None


def test_a_raise_pays_only_when_the_last_one_raised_the_measured_rate_by_a_fifth():
    assert chain.raise_pays({}, 4) and chain.raise_pays({4: 0.2}, 4)  # never raised: tried
    assert not chain.raise_pays({2: 0.2}, 4)  # raised to 4 but not measured there yet: wait
    assert chain.raise_pays({2: 0.2, 4: 0.4}, 4) and chain.raise_pays({2: 0.2, 4: 0.25}, 4)
    assert not chain.raise_pays({2: 0.2, 4: 0.21}, 4)



def test_the_database_is_pressed_by_lock_waits_or_by_connections_and_pressure_takes_the_worse():
    ok = {"active": 4, "connections": 20, "max_connections": 100, "lock_waiters": 0, "longest_wait": 0.0}
    assert chain.db_level(**ok) == "ok"
    assert chain.db_level(**{**ok, "lock_waiters": 3}) == "high"
    assert chain.db_level(**{**ok, "lock_waiters": 1, "longest_wait": 75.0}) == "high"
    assert chain.db_level(**{**ok, "connections": 80}) == "high"
    assert chain.worst("low", "high") == "high" and chain.worst("high", "ok") == "high"
    assert chain.worst("low", "ok") == "low" and chain.worst("ok", "ok") == "ok"
    assert chain.database_load(None) is None


def test_workers_fall_while_the_database_is_locking_even_when_the_machine_has_room(monkeypatch, tmp_path):
    monkeypatch.setattr(chain, "step_log_text", lambda name: LOG)  # many bundles: a move loses only those in flight
    steps = [_step("a1", "A", minutes=600), _step("b1", "B", minutes=60)]
    for step in steps:
        step["workers"] = 8
    state, started, killed, now = _timed(monkeypatch, tmp_path, steps, ticks=10)
    monkeypatch.setattr(chain, "machine_pressure", lambda relaxed=False: "low")
    locking = {"active": 9, "connections": 30, "max_connections": 100, "lock_waiters": 5, "longest_wait": 90.0}
    quiet = {**locking, "lock_waiters": 0, "longest_wait": 0.0}
    readings = iter([quiet, quiet])  # both steps start while the store is quiet, then it locks
    monkeypatch.setattr(chain, "database_load", lambda reader_url: next(readings, locking))
    _run_auto(steps, state, slots=2, deadline=now["t"] + chain.timedelta(minutes=45), reader_url="x")
    assert started[:2] == [("a1", 8), ("b1", 8)]
    assert ("b1", 4) in started  # the shortest chain halved while the store was locking, with the machine at `low`


STATE = """11-18 06:33:30 ET a1 attempt 1 start
11-18 06:43:30 ET a1 done: Done
11-18 06:43:31 ET a2 attempt 1 start
11-18 07:13:31 ET a2 attempt 1 stopped rc=1: x
11-18 07:13:32 ET a2 attempt 2 start
11-18 07:23:31 ET a2 done: Done
"""


def test_a_steps_measured_time_runs_from_its_first_start_to_its_done_line():
    assert chain.measured(STATE) == {"a1": 10.0, "a2": 40.0}


def test_a_step_not_done_is_estimated_from_how_fast_the_done_ones_ran_against_their_bounds():
    steps = [_step("a1", "A", minutes=100), _step("a2", "A", minutes=200), _step("b1", "B", minutes=400)]
    estimate = chain.estimates(steps, {"a1": 10.0, "a2": 40.0})
    assert estimate["a1"] == 10.0 and estimate["a2"] == 40.0  # what ran
    assert estimate["b1"] == pytest.approx(400 * 0.15)  # the median of 10/100 and 40/200 is 0.15 of the bound
    assert chain.estimates(steps, {})["b1"] == 400  # nothing measured: the bound


def test_the_projected_finish_is_the_longest_chain_left_less_what_a_running_step_has_done():
    steps = [_step("a1", "A"), _step("a2", "A"), _step("b1", "B")]
    estimate = {"a1": 10.0, "a2": 40.0, "b1": 100.0}
    assert chain.remaining(steps, done=set(), running={}, estimate=estimate) == 100.0  # b1 alone is longer than a1+a2
    assert chain.remaining(steps, done={"a1"}, running={"b1": 70.0}, estimate=estimate) == 40.0  # b1 has 30 left, a2 40
    assert chain.remaining(steps, done={"a1", "a2", "b1"}, running={}, estimate=estimate) == 0.0
    # b1 is 150 minutes in against an estimate of 100 and a bound of 400 (the `_step` default is 60: give it its own)
    steps[2]["minutes"] = 400
    assert chain.remaining(steps, done={"a1", "a2"}, running={"b1": 150.0}, estimate=estimate) == 250.0  # its bound, less used


def test_priority_uses_the_measured_time_when_it_is_given():
    steps = [_step("short_bound", "A", minutes=10), _step("long_bound", "B", minutes=500)]
    assert chain.chain_length(steps)["long_bound"] == 500
    assert chain.chain_length(steps, {"short_bound": 300.0, "long_bound": 20.0}) == {"short_bound": 300.0, "long_bound": 20.0}


def test_room_to_scale_up_needs_connections_below_the_target_as_well_as_a_machine_with_room():
    assert chain.room("low", connections=40, target=250) == "low"
    assert chain.room("low", connections=250, target=250) == "ok"  # the target is used: more workers add nothing
    assert chain.room("high", connections=10, target=250) == "high"
    assert chain.room("ok", connections=10, target=250) == "ok"


LOG = """Delivery of 2026-06-30, read from the capture: revision 1
ipo silver: 149 documents in 149 bundles, 1 at once
Bundle 1/149: 512 of 512 documents to load
  run a complete in 1.6 min
Bundle 2/149: 512 of 512 documents to load
  run b complete in 1.4 min
Bundle 3/149: 512 of 512 documents to load
"""


def test_a_multi_bundle_logs_progress_is_the_bundles_it_has_completed_of_the_total():
    assert chain.bundle_progress(LOG) == (2, 149)
    assert chain.bundle_progress("gleif mastering: 1 documents in 1 bundles\nBundle 1/1: 1 of 1 documents to load\n") == (0, 1)
    assert chain.bundle_progress("") is None


def test_the_minutes_left_follow_the_rate_so_far_and_are_unknown_before_one_bundle_is_done():
    assert chain.minutes_left(done=2, total=149, elapsed=10.0, ran=2) == 735.0  # five minutes a bundle, 147 to go
    assert chain.minutes_left(done=0, total=149, elapsed=10.0, ran=0) is None
    assert chain.minutes_left(done=149, total=149, elapsed=700.0, ran=149) == 0.0
    assert chain.minutes_left(done=120, total=149, elapsed=7.0, ran=0) is None  # nothing run yet this attempt: no rate


LOCK_WAITING = {"active": 1, "idle_in_transaction": 0, "lock_waiting": 1, "changed_min": 0.1, "statement": "update silver.t", "wait": "Lock:transactionid"}


def test_a_step_is_progressing_waiting_on_locks_or_possibly_stalled_by_its_own_evidence():
    busy = {"elapsed": 30.0, "bound": 480, "log_age": 40.0, "cpu": 85.0, "lock_waiters": 0}
    assert chain.verdict(**busy).startswith("progressing")
    assert chain.verdict(**{**busy, "cpu": 0.0}).startswith("no sign of work")  # silent log too
    assert chain.verdict(**{**busy, "cpu": 0.0, "log_age": 2.0}).startswith("progressing")  # log moved
    assert chain.verdict(**{**busy, "lock_waiters": 3}).startswith("progressing")  # the store's waiters are a neighbour's, not this step's
    assert chain.verdict(**{**busy, "lock_waiters": 3}, evidence=LOCK_WAITING).startswith("waiting on database locks")
    assert "past its bound of 480 min" in chain.verdict(**{**busy, "elapsed": 500.0})


def test_the_database_writes_a_minute_come_from_two_cumulative_counts():
    assert chain.writes_per_minute({"mdm": 1000, "silver": 50}, {"mdm": 1500, "silver": 50}, seconds=30.0) == {"mdm": 1000.0, "silver": 0.0}
    assert chain.writes_per_minute({"mdm": 10}, {}, seconds=30.0) == {"mdm": 0.0}


def test_cpu_percent_comes_from_the_cpu_time_used_in_the_window_not_a_lifetime_average():
    assert chain.cpu_seconds("0:00.50\n1:02.25\n") == 62.75
    assert chain.cpu_seconds("1:01:01.5") == 3661.5
    assert chain.cpu_percent(before=100.0, after=118.0, seconds=20.0) == 90.0
    assert chain.cpu_percent(before=100.0, after=100.0, seconds=20.0) == 0.0


def test_a_step_is_judged_by_the_store_it_writes_and_one_waiting_session_is_not_a_lock_problem():
    assert chain.store_of("silver") == "silver" and chain.store_of("mastering") == "mdm" and chain.store_of("custodians") == "mdm"
    busy = {"elapsed": 30.0, "bound": 480, "log_age": 40.0, "cpu": 0.0}
    assert chain.verdict(**busy, lock_waiters=1).startswith("no sign of work")  # one waiter is normal
    assert chain.verdict(**busy, lock_waiters=3).startswith("no sign of work")  # three waiters elsewhere do not lock this step
    assert chain.verdict(**busy, lock_waiters=3, evidence=LOCK_WAITING).startswith("waiting on database locks")
    assert chain.verdict(**busy, lock_waiters=1, evidence=LOCK_WAITING).startswith("waiting on database locks") is False


def test_a_step_that_cannot_finish_in_the_attempts_it_has_left_says_so():
    assert chain.outlook(left=252.0, elapsed=22.0, bound=60, attempt=2, attempts=3) == \
        "needs about 252 min but has 98 min left in its 1 remaining attempts: raise its workers or its minutes"
    assert chain.outlook(left=30.0, elapsed=22.0, bound=60, attempt=2, attempts=3) == ""
    assert chain.outlook(left=None, elapsed=22.0, bound=60, attempt=2, attempts=3) == ""


def test_a_stores_sessions_are_counted_by_what_they_wait_for_and_mostly_waiting_on_the_client_means_client_bound():
    rows = [("mdm", "active", 3), ("mdm", "idle", 29), ("mdm", "idle in transaction", 5), ("silver", "active", 4),
            ("silver", "idle", 1)]
    summary = chain.session_summary(rows)
    assert summary["mdm"] == {"active": 3, "waiting_on_client": 34}  # idle and idle in transaction both wait on the client
    assert chain.session_note("mdm", summary["mdm"]) == "mdm: 3 sessions working, 34 waiting on the client: client-bound, not the database"
    assert chain.session_note("silver", summary["silver"]) == "silver: 4 sessions working, 1 waiting on the client"
    assert chain.session_summary([]) == {}


def test_a_verdict_never_says_unclear_whatever_the_store_shares():
    quiet = dict(elapsed=120.0, bound=480, log_age=120.0, cpu=0.0, lock_waiters=0)
    assert chain.verdict(**quiet, evidence=None).startswith("no sign of work")
    working = {"active": 1, "idle_in_transaction": 0, "changed_min": 0.03, "statement": "insert silver.t", "wait": "IO:DataFileRead"}
    assert chain.verdict(**quiet, evidence=working).startswith("past its bound of 480 min") is False
    assert "progressing" in chain.verdict(**quiet, evidence=working)


RESUMED = """Bundle 1/149: all 512 documents already loaded
Bundle 2/149: all 512 documents already loaded
Bundle 3/149: 512 of 512 documents to load
  run c complete in 1.5 min
Bundle 4/149: 512 of 512 documents to load
"""


def test_bundles_already_loaded_by_an_earlier_attempt_count_as_done():
    assert chain.bundle_progress(RESUMED) == (3, 149)  # two skipped and one completed
    assert chain.bundles_run(RESUMED) == 1  # only the completed one took this attempt's time
    # the rate is this attempt's minutes over the bundles it ran, never over the ones it skipped
    assert chain.minutes_left(done=3, total=149, elapsed=4.5, ran=1) == 657.0


def test_a_store_is_client_bound_when_more_than_half_its_sessions_wait_on_the_client():
    assert chain.session_note("mdm", {"active": 10, "waiting_on_client": 30}).endswith("client-bound, not the database")
    assert chain.session_note("mdm", {"active": 10, "waiting_on_client": 11}).endswith("client-bound, not the database")
    assert not chain.session_note("mdm", {"active": 10, "waiting_on_client": 9}).endswith("not the database")


def test_cpu_over_the_window_counts_only_processes_present_in_both_readings():
    assert chain.window_cpu({1: 100.0, 2: 50.0}, {1: 118.0, 2: 50.0, 3: 9000.0}) == 18.0  # pid 3 began in the window
    assert chain.window_cpu({}, {1: 5.0}) == 0.0


def test_only_a_chain_loads_own_processes_are_matched_by_command_line():
    assert chain.is_load_process("/x/python -c from edgar_warehouse.cli import main; ... rules run --source gleif --target mastering", "gleif", "mastering")
    assert chain.is_load_process("uv run --no-sync edgar-warehouse load --source gleif --target mastering --capture /c", "gleif", "mastering")
    assert not chain.is_load_process("vim --source gleif --target mastering", "gleif", "mastering")  # not the platform's
    assert not chain.is_load_process("edgar-warehouse load --source gleif --target silver", "gleif", "mastering")


def test_a_workers_range_follows_the_tasks_memory_and_vcpus_not_a_fixed_two_to_eight():
    """A worker is sized at half a gigabyte, and a vCPU carries four workers that wait on the database."""
    assert chain.workers_range(vcpu=0.5, memory_gb=1) == (1, 2)  # an AWS small task
    assert chain.workers_range(vcpu=1, memory_gb=4) == (1, 4)  # medium: four vCPU-shares of workers, memory for eight
    assert chain.workers_range(vcpu=2, memory_gb=8) == (1, 8)  # large
    assert chain.workers_range(vcpu=16, memory_gb=64) == (1, 64)  # a bigger task goes past eight
    assert chain.workers_range(vcpu=0.25, memory_gb=0.25) == (1, 1)  # never below one


def test_the_chain_file_names_the_aws_task_sizes_the_state_machines_run_on():
    profiles = chain.capacity_profiles()
    assert profiles["aws-small"] == {"vcpu": 0.5, "memory_gb": 1}
    assert profiles["aws-medium"] == {"vcpu": 1, "memory_gb": 4}
    assert profiles["aws-large"] == {"vcpu": 2, "memory_gb": 8}


def test_a_capacity_name_gives_its_bounds_and_the_machine_gives_its_own(monkeypatch):
    assert chain.bounds_for("aws-large") == (1, 8)
    assert chain.bounds_for("aws-medium") == (1, 4)
    monkeypatch.setattr(chain.os, "cpu_count", lambda: 8)
    monkeypatch.setattr(chain, "physical_gb", lambda: 8.0)
    assert chain.bounds_for("local") == (1, 8)  # half the machine's memory: 4 GB, 8 workers
    monkeypatch.setattr(chain, "physical_gb", lambda: 4.0)
    assert chain.bounds_for("local") == (1, 4)
    try:
        chain.bounds_for("aws-huge")
    except SystemExit as unknown:
        assert "aws-huge" in str(unknown)
    else:
        raise AssertionError("an unknown capacity must be refused")


def test_a_started_step_is_held_to_the_profiles_range(monkeypatch, tmp_path):
    steps = [_step("a1", "A", minutes=600)]
    steps[0]["workers"] = 8  # the load jobs file asks for eight; a small task carries two
    state, started, killed, now = _timed(monkeypatch, tmp_path, steps, ticks=10)
    monkeypatch.setattr(chain, "machine_pressure", lambda relaxed=False: "ok")
    _run_auto(steps, state, slots=2, deadline=now["t"] + chain.timedelta(minutes=20), bounds=(1, 2))
    assert started[0] == ("a1", 2)


def test_a_started_step_is_told_the_capacity_it_runs_on_so_its_own_check_uses_the_same_range(monkeypatch, tmp_path):
    commands = []
    steps = [_step("a1", "A", minutes=600)]
    state, started, killed, now = _timed(monkeypatch, tmp_path, steps, ticks=10)
    original = chain.subprocess.Popen
    monkeypatch.setattr(chain.subprocess, "Popen", lambda command, **kw: commands.append(command) or original(command, **kw))
    monkeypatch.setattr(chain, "machine_pressure", lambda relaxed=False: "ok")
    _run_auto(steps, state, slots=2, deadline=now["t"] + chain.timedelta(minutes=20), bounds=(1, 4), capacity="aws-medium")
    assert commands[0][commands[0].index("--capacity") + 1] == "aws-medium"


def test_every_run_mode_holds_a_steps_workers_to_the_capacity_not_only_the_scheduler():
    steps = [{"name": "gleif", "workers": 8}, {"name": "small", "workers": 2}, {"name": "tiny", "workers": 1}]
    assert [s["workers"] for s in chain.clamped(steps, "local", capacity=(1, 4.0))] == [4, 2, 1]  # a medium task starts GLEIF at 4
    assert [s["workers"] for s in chain.clamped(steps, "local", capacity=(2, 8.0))] == [8, 2, 1]  # and a larger one at 8
    assert steps[0]["workers"] == 8  # the load jobs file's own steps are not changed


def test_a_state_file_from_another_store_is_set_aside_so_its_done_lines_never_satisfy_a_wait(tmp_path):
    state = tmp_path / "chain.log"
    state.write_text("11-15 14:21:31 ET chain store aaaa1111\n11-15 14:21:31 ET company done: Done\n")
    assert chain.ensure_store(state, "bbbb2222") == "set aside"  # a different store: the old lines are archived
    assert chain.done_steps(state) == set()
    assert state.read_text().endswith("chain store bbbb2222 generation ?\n")
    assert (tmp_path / "chain.log.aaaa1111").read_text().count("company done") == 1
    state.write_text(state.read_text() + "11-18 06:40:00 ET company done: Done\n")
    assert chain.ensure_store(state, "bbbb2222") == "same"  # the same store: nothing is touched
    assert chain.done_steps(state) == {"company"}
    fresh = tmp_path / "new.log"
    assert chain.ensure_store(fresh, "bbbb2222") == "fresh" and fresh.read_text().endswith("chain store bbbb2222 generation ?\n")


def test_a_state_file_with_lines_and_no_marker_is_set_aside_and_kept_never_trusted_and_never_a_reason_to_stop(tmp_path):
    """An old run's file under the same label (a hand-chosen name can repeat) must not stop a load or satisfy its waits."""
    state = tmp_path / "chain.log"
    state.write_text("11-15 14:21:31 ET company done: Done\n")
    assert chain.ensure_store(state, "bbbb2222") == "set aside"  # no marker: its done lines are not this store's to trust
    assert chain.done_steps(state) == set() and state.read_text().endswith("chain store bbbb2222 generation ?\n")
    kept = [p for p in tmp_path.glob("chain.log.*") if p.suffix != ".lock"]
    assert [p.name for p in kept] == ["chain.log.unmarked"] and kept[0].read_text() == "11-15 14:21:31 ET company done: Done\n"  # kept
    state.write_text("11-15 14:21:31 ET company done: Done\n")  # a second old file under the same label: nothing is overwritten
    assert chain.ensure_store(state, "bbbb2222") == "set aside"
    assert sorted(p.name for p in tmp_path.glob("chain.log.*") if p.suffix != ".lock") == ["chain.log.unmarked", "chain.log.unmarked.2"]
    adopted = tmp_path / "adopt.log"
    adopted.write_text("11-15 14:21:31 ET company done: Done\n")
    assert chain.ensure_store(adopted, "bbbb2222", adopt=True) == "adopted"  # the operator's word keeps it, as before
    assert chain.done_steps(adopted) == {"company"} and chain.ensure_store(adopted, "bbbb2222") == "same"


def test_a_reset_store_at_the_same_address_is_another_store_so_a_reused_label_skips_nothing(tmp_path):
    """The address names the instance, and a reset keeps it: the database's creation identity says the data went."""
    state = tmp_path / "chain.log"
    assert chain.ensure_store(state, "bbbb2222", generation="1001") == "fresh"
    assert state.read_text().endswith("chain store bbbb2222 generation 1001\n")
    state.write_text(state.read_text() + "11-18 06:40:00 ET company done: Done\n")
    assert chain.ensure_store(state, "bbbb2222", generation="1001") == "same"
    assert chain.ensure_store(state, "bbbb2222", generation="") == "same"  # unreadable now: never archive a running load's file
    assert chain.done_steps(state) == {"company"}
    assert chain.ensure_store(state, "bbbb2222", generation="2002") == "set aside"  # the databases were made again
    assert chain.done_steps(state) == set()
    assert state.read_text().endswith("chain store bbbb2222 generation 2002\n")
    assert (tmp_path / "chain.log.bbbb2222-1001").read_text().count("company done") == 1
    older = tmp_path / "older.log"
    older.write_text("11-15 14:21:31 ET chain store bbbb2222\n11-15 14:21:31 ET company done: Done\n")  # a marker with no generation
    assert chain.ensure_store(older, "bbbb2222", generation="3003") == "set aside"  # it cannot show the store was not made again


def test_the_database_generation_is_unreadable_as_an_empty_string_never_an_error_or_an_address(monkeypatch):
    import psycopg2

    def refuse(*args, **kwargs):
        raise psycopg2.OperationalError("could not connect to server at an-address")

    monkeypatch.setattr(psycopg2, "connect", refuse)
    assert chain.database_generation("postgresql+psycopg2://u:p@h.invalid:5432/mdm") == ""


def test_two_lanes_starting_at_once_against_another_stores_file_set_it_aside_once_and_lose_nothing(tmp_path):
    import threading

    state = tmp_path / "chain.log"
    state.write_text("11-15 14:21:31 ET chain store aaaa1111\n11-15 14:21:31 ET company done: Done\n")
    results, start = [], threading.Barrier(2)

    def lane():
        start.wait()
        results.append(chain.ensure_store(state, "bbbb2222"))

    threads = [threading.Thread(target=lane) for _ in range(2)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(results) == ["same", "set aside"]
    assert (tmp_path / "chain.log.aaaa1111").read_text().count("company done") == 1  # the archive kept its lines
    assert state.read_text().count("chain store bbbb2222") == 1


def test_a_store_is_named_by_its_address_without_ever_showing_it():
    one = chain.store_id("postgresql://a:secret@host-one.invalid:5432/mdm")
    assert one == chain.store_id("postgresql+psycopg2://b:other@HOST-ONE.invalid:5432/silver")  # any login, database or case
    assert one == chain.store_id("postgresql://a:secret@host-one.invalid/mdm")  # the default port is 5432
    assert one != chain.store_id("postgresql://a:secret@host-two.invalid:5432/mdm")
    assert len(one) == 8 and "host-one" not in one and "secret" not in one
    assert chain.store_id("postgresql://u:pa/ss@host-one.invalid:5432/mdm") == one  # an unescaped slash in a password


def test_a_url_that_names_no_host_is_an_error_not_a_shared_name_and_a_socket_names_its_directory():
    import pytest

    for url in ("", "postgresql:///mdm", "not a url"):
        with pytest.raises(ValueError, match="names no host"):
            chain.store_id(url)
    assert chain.store_id("postgresql:///mdm?host=/var/run/pg-a") != chain.store_id("postgresql:///mdm?host=/var/run/pg-b")


def test_a_retry_is_pointless_only_when_the_same_error_comes_back_with_nothing_moved_and_not_a_lock_or_the_window():
    error = "ValueError: Step sec_tickers: no document of the bundle matches '*company_tickers_exchange*'"
    assert chain.retry_is_pointless(error, error)
    assert chain.retry_is_pointless("Blocked: silver.t: refused (SQLSTATE 42501)", "Blocked: silver.t: refused (SQLSTATE 42501)")
    assert not chain.retry_is_pointless("", error)  # a first failure is retried, unless it names a cause that never clears
    stopped = "Load stopped: 146 of 150 did not finish: bundle 1: rules run --source failed with status 1"
    refused = "Traceback ...\nValueError: Source native revision has contradictory publications: a record of this revision"
    assert chain.retry_is_pointless("", stopped, refused)  # the same inputs give the same refusal: a retry only adds runs
    assert not chain.retry_is_pointless("", stopped, "OperationalError: server closed the connection unexpectedly")
    kept = "$ rules run\nTraceback\n  File x\n" + "ValueError: Source native revision has contradictory publications\n" * 3
    assert chain.cause_of(kept) == "3 times: ValueError: Source native revision has contradictory publications"
    assert chain.cause_of("nothing raised here") == ""
    assert not chain.retry_is_pointless(error, "ValueError: another failure")
    late = "Load stopped: 2 of 149 did not finish: bundle 42 did not finish before the deadline"
    assert not chain.retry_is_pointless(late, late)  # the window ran out; the next attempt resumes where it stopped
    moved = ("Load stopped: 1 of 149 did not finish: bundle 17: DeadlockDetected",
             "Load stopped: 1 of 149 did not finish: bundle 230: DeadlockDetected")
    assert not chain.retry_is_pointless(*moved)  # the bundle moved: it is making progress
    for locked in ("DeadlockDetected: deadlock detected", "LockNotAvailable: canceling statement due to lock timeout",
                   "OperationalError: could not connect to server", "connection timed out"):
        assert not chain.retry_is_pointless(locked, locked), locked  # these clear when the other load ends


def test_the_errors_an_attempt_wrote_to_the_shared_error_log_are_kept_with_that_step_and_not_another_lanes(tmp_path):
    log = tmp_path / "load-errors.log"
    log.write_text("$ old command\nOldError: before this attempt\n")
    offset = (log.stat().st_ino, log.stat().st_size)
    log.write_text(log.read_text()
                   + "$ rules run --source sec.x --target mastering --work-run-id r\nValueError: postgresql://u:pw@h:5432/db failed\n"
                   + "$ mdm prepare-capture --source openfigi --target mastering --capture /c\nKeyError: another lane's block\n")
    kept = chain.errors_since(log, offset, "sec.x", "mastering")
    assert "ValueError" in kept and "OldError" not in kept and "another lane" not in kept
    assert "pw" not in kept and "<addr>" in kept
    assert "another lane" in chain.errors_since(log, offset)  # with no step named, every block since the offset
    assert chain.errors_since(tmp_path / "missing.log", (0, 0), "sec.x", "mastering") == ""


def test_ipo_has_a_window_that_fits_its_bundles_and_runs_several_at_once():
    ipo = BY_NAME["ipo"]
    assert ipo["minutes"] * ipo["attempts"] >= 300  # 149 bundles at about two minutes each, one at a time
    assert ipo["bundles"] >= 4  # measured: one at a time took 181 minutes with the machine idle


def test_redaction_hides_every_address_form_and_every_value_named_like_a_secret():
    text = ("ValueError: postgresql+psycopg2://u:pw1@h.invalid:5432/mdm and postgres://v:pw2@h2.invalid/x and https://a:b@c.invalid/p; "
            "host=h.invalid password=pw3 dsn=postgresql://w:pw4@h3.invalid/y token: abc123 api_key='k-5' SECRET=s6 url=http://z.invalid")
    hidden = chain.redact(text)
    for leaked in ("pw1", "pw2", "pw3", "pw4", "abc123", "k-5", "s6", "h.invalid", "h2.invalid", "h3.invalid", "z.invalid", "u:", "b@c"):
        assert leaked not in hidden, (leaked, hidden)
    assert "ValueError" in hidden and "<addr>" in hidden and "<hidden>" in hidden


PS = """  100     1 0:10.00  50000 uv run --no-sync edgar-warehouse load --source gleif --target mastering --capture /c
  101   100 14:00.00 80000 /x/python /x/edgar_warehouse/driver.py
  102   101 3:00.00  90000 /x/python -c from edgar_warehouse.cli import main; ... rules run --source gleif --target mastering
  103   102 15:50.00 40000 /x/python -c from multiprocessing.spawn import spawn_main; spawn_main(tracker_fd=5)
  104   102 15:40.00 41000 /x/python -c from multiprocessing.spawn import spawn_main; spawn_main(tracker_fd=5)
  200     1 9:00.00  60000 /x/python -c from edgar_warehouse.cli import main; ... rules run --source other --target silver
  201   200 5:00.00  60000 /x/python -c from multiprocessing.spawn import spawn_main; spawn_main(tracker_fd=5)
"""


def test_a_loads_processes_include_the_workers_it_started_whose_command_lines_name_no_source():
    pids = chain.load_pids(PS, "gleif", "mastering")
    assert sorted(pids) == [100, 101, 102, 103, 104]  # the two spawned workers count; the other load's do not
    assert chain.load_pids(PS, "other", "silver") == {200: 540.0, 201: 300.0}
    assert chain.load_pids("", "gleif", "mastering") == {}


def test_a_workers_range_can_use_a_steps_measured_memory_not_only_the_default_share():
    assert chain.workers_range(vcpu=8, memory_gb=4) == (1, 8)  # the default half gigabyte a worker: eight
    assert chain.workers_range(vcpu=8, memory_gb=4, worker_gb=0.1) == (1, 32)  # measured at 100 MB: four to a vCPU, 32
    steps = [{"name": "gleif", "workers": 16, "worker_gb": 0.1}, {"name": "plain", "workers": 16}]
    held = chain.clamped(steps, "local", capacity=(8, 4.0))
    assert [s["workers"] for s in held] == [16, 8]  # GLEIF keeps its 16; a step with no measure is held to eight
    assert [s["workers"] for s in chain.clamped(steps, "local", capacity=(1, 2.0))] == [4, 4]  # a 1 vCPU, 2 GB machine


def test_the_status_header_says_writes_are_counted_at_commit(tmp_path, monkeypatch):
    monkeypatch.setattr(chain, "external_loads", lambda: set())
    header = chain.status([], tmp_path / "state.log", None, sample=0)[0]
    assert "counted when a transaction commits" in header and "0 running" in header


def test_the_workers_a_load_runs_with_are_read_from_its_command_line_not_the_chain_file():
    assert chain.load_workers(PS.replace("--capture /c", "--capture /c --workers 8"), "gleif", "mastering") == 8
    assert chain.load_workers(PS, "gleif", "mastering") is None  # no --workers flag on that line
    assert chain.load_workers(PS, "none", "mastering") is None


def test_the_skills_that_operate_and_recover_loads_point_to_the_one_root_cause_method():
    method = ROOT / "skills/data-platform/ROOT-CAUSE.md"
    assert method.exists()
    text = method.read_text()
    for needed in ("Doubt the instrument first", "answer each why from evidence", "Four lines in business words", "never the chain"):
        assert needed.lower() in text.lower(), needed
    for skill in ("data-platform", "data-operations", "bookkeeping", "data-onboarding", "refining-rules", "data-profiling",
                  "data-quality", "change-journal"):
        assert "ROOT-CAUSE.md" in (ROOT / f"skills/{skill}/SKILL.md").read_text(), skill  # linked, never copied


def test_a_cpu_time_with_days_is_read_and_one_unreadable_row_never_breaks_the_listing():
    assert chain.cpu_seconds("1-02:03:04") == 86400 + 2 * 3600 + 3 * 60 + 4
    listing = "  1     0 1-02:03:04 100 /usr/sbin/other\n  100   1 0:10.00 50000 uv run edgar-warehouse load --source gleif --target mastering\n  101   100 not-a-time 1 worker\n"
    assert chain.load_pids(listing, "gleif", "mastering") == {100: 10.0, 101: 0.0}  # a bad time is zero, never an exception


def test_a_listing_row_with_no_arguments_still_reaches_its_workers():
    listing = "  100     1 0:10.00  50000\n  101   100 5:00.00  9000 /x/python -c from multiprocessing.spawn import spawn_main\n"
    assert chain.load_pids(listing, "gleif", "mastering") == {}  # nothing names the load: no match, and no crash
    listing += "  102     1 0:01.00  50000 uv run edgar-warehouse load --source gleif --target mastering\n  103   102 7:00.00 9000\n"
    assert sorted(chain.load_pids(listing, "gleif", "mastering")) == [102, 103]  # a blank-args child of the driver is its worker


def test_a_worker_memory_that_is_not_a_positive_finite_number_is_refused_and_the_division_is_exact(tmp_path):
    import pytest

    assert chain.workers_range(vcpu=8, memory_gb=4.0, worker_gb=0.4) == (1, 10)  # 4.0 // 0.4 is 9.0 in floating point
    for bad in (0, -1, float("inf"), float("nan"), 1e9):
        path = tmp_path / "chain.yaml"
        path.write_text(yaml.safe_dump({"defaults": {"workers": 2, "bundles": 1}, "capture_label": "l", "steps": [
            {"name": "x", "minutes": 60, "worker_gb": bad}]}))
        with pytest.raises(ValueError, match="worker_gb"):
            chain.load_jobs(path)


def test_the_start_count_and_the_rescale_use_each_steps_own_measured_range(monkeypatch, tmp_path):
    steps = [_step("gleif", "A", minutes=600), _step("plain", "B", minutes=60)]
    steps[0].update(workers=16, worker_gb=0.4)
    steps[1].update(workers=16)
    monkeypatch.setattr(chain, "capacity_of", lambda name: (8, 4.0))  # 4 GB: GLEIF carries 10, a half-gigabyte worker 8
    state, started, killed, now = _timed(monkeypatch, tmp_path, steps, ticks=10)
    monkeypatch.setattr(chain, "machine_pressure", lambda relaxed=False: "ok")
    _run_auto(steps, state, slots=2, deadline=now["t"] + chain.timedelta(minutes=30))
    assert dict(started) == {"gleif": 10, "plain": 8}
    assert chain.rescale({"gleif": 5}, {"gleif": 1}, "low", {"gleif": (1, 10)}) == ("gleif", 10)
    assert chain.rescale({"gleif": 5}, {"gleif": 1}, "low", {"gleif": (1, 8)}) == ("gleif", 8)


STEP_LOG = """Bundle 1/2: 512 of 512 documents to load
  run 11111111-1111-4111-8111-111111111111 complete in 1.6 min
Bundle 2/2: 512 of 512 documents to load
  run 22222222-2222-4222-8222-222222222222 complete in 1.4 min
Done: 1024 documents loaded, 0 already loaded before
"""


def test_the_run_to_publish_is_the_last_one_a_step_completed():
    assert chain.last_run_id(STEP_LOG) == "22222222-2222-4222-8222-222222222222"
    assert chain.last_run_id("Done: 1 documents loaded\n") is None  # a step that finished with no run of its own publishes nothing
    assert chain.last_run_id("") is None


def test_only_the_catalogs_address_and_token_reach_the_status_command_and_only_when_both_are_set(tmp_path):
    env = tmp_path / ".env"
    env.write_text("export OPENMETADATA_URL=http://127.0.0.1:8587/api\nOPENMETADATA_TOKEN='t-invented'\n"
                   "OPENMETADATA_ADMIN_PASSWORD=never-passed\nSOMETHING_ELSE=x\n")
    assert chain.catalog_env(env) == {"OPENMETADATA_URL": "http://127.0.0.1:8587/api", "OPENMETADATA_TOKEN": "t-invented"}
    env.write_text("OPENMETADATA_URL=http://127.0.0.1:8587/api\n")
    assert chain.catalog_env(env) == {}  # no token: nothing is published, and nothing is partly set
    assert chain.catalog_env(tmp_path / "missing.env") == {}


def test_the_catalogs_answer_is_read_as_published_or_not_with_its_cause_and_never_raises():
    confirmed = '{"ok": true, "status": "confirmed", "pipeline_status": {"execution_status": "Successful", "failed_tasks": 0}}'
    assert chain.catalog_outcome(confirmed) == "confirmed as Successful"
    assert chain.catalog_outcome(confirmed.replace("Successful", "Pending")) == "confirmed as Pending"
    assert chain.catalog_outcome('{"cause": "OpenMetadata endpoint did not answer", "ok": false, "status": "failed"}') == \
        "not published: OpenMetadata endpoint did not answer"
    assert chain.catalog_outcome("not json at all") == "not published: no readable answer"
    assert chain.catalog_outcome("") == "not published: no readable answer"
    assert chain.catalog_outcome(confirmed + "\n}") == "confirmed as Successful"  # a stray brace after the answer


def test_a_finished_step_never_calls_the_catalog_and_a_catch_up_is_its_own_command():
    """The catalog describes a load and takes no part in it: the step loop names no catalog, and `--catalog-status` publishes later."""
    import inspect
    assert "catalog" not in inspect.getsource(chain.attempt_loop).lower() and not hasattr(chain, "after_done")
    assert "--catalog-status" in inspect.getsource(chain.main)


def test_a_catch_up_publishes_the_status_of_every_step_already_done_from_its_own_log(monkeypatch, tmp_path):
    state = tmp_path / "chain.log"
    state.write_text("11-18 06:40:00 ET a1 done: Done\n11-18 06:50:00 ET b1 done: Done\n")
    (tmp_path / "chain-fresh-v1-a1.log").write_text(STEP_LOG)
    monkeypatch.setattr(chain, "LOGS", tmp_path)
    monkeypatch.setattr(chain, "RUN", "fresh-v1")
    monkeypatch.setattr(chain, "note", lambda message, path: None)
    seen = []
    monkeypatch.setattr(chain, "publish_catalog_status", lambda step: seen.append(step["name"]) or "published to svc.t")
    steps = [_step("a1", "A"), _step("b1", "B"), _step("c1", "C")]
    assert chain.catch_up(steps, state) == {"a1": "published to svc.t", "b1": "published to svc.t", "c1": None}
    assert seen == ["a1", "b1"]  # c1 is not done: nothing to say


def test_the_status_command_gets_a_short_environment_the_bookkeeping_login_and_the_catalog_and_nothing_else():
    base = {"PATH": "/bin", "HOME": "/h", "AWS_SECRET_ACCESS_KEY": "no", "SOME_DATABASE_URL": "no", "OPENMETADATA_ADMIN_PASSWORD": "no"}
    worker = {"DATA_URL": "postgresql://b:p@h/data", "CONTROL_URL": "postgresql://b:p@h/control", "BOOKKEEPING_MANIFEST_ROOT": "file:///x",
              "OTHER_SECRET": "no"}
    catalog = {"OPENMETADATA_URL": "http://127.0.0.1:8587/api", "OPENMETADATA_TOKEN": "t"}
    given = chain.status_env(base, worker, catalog)
    assert set(given) == {"PATH", "HOME", "DATA_URL", "CONTROL_URL", "OPENMETADATA_URL", "OPENMETADATA_TOKEN"}
    assert "no" not in given.values()  # no other login, key or password reaches it


def test_a_step_that_loaded_nothing_new_in_its_last_attempt_publishes_the_run_of_an_earlier_one(tmp_path, monkeypatch):
    monkeypatch.setattr(chain, "LOGS", tmp_path)
    monkeypatch.setattr(chain, "RUN", "fresh-v1")
    (tmp_path / "chain-fresh-v1-a1.log").write_text("Bundle 1/1: all 5 documents already loaded\nDone: 0 documents loaded, 5 already loaded before\n")
    (tmp_path / "chain-fresh-v1-a1.log.attempt-1").write_text(STEP_LOG.replace("22222222", "33333333"))
    (tmp_path / "chain-fresh-v1-a1.log.attempt-2").write_text(STEP_LOG)
    assert chain.step_run_id("a1") == "22222222-2222-4222-8222-222222222222"  # its newest attempt that ran one
    assert chain.step_run_id("none") is None
    (tmp_path / "chain-fresh-v1-a1.log.attempt-1.errors").write_text("a failed attempt's captured errors")  # not an attempt's log
    assert chain.step_run_id("a1") == "22222222-2222-4222-8222-222222222222"


def test_a_bad_line_in_the_env_file_never_hides_the_catalog_pair(tmp_path):
    env = tmp_path / ".env"
    env.write_text("STUB_NOTE=it's\nOPENMETADATA_URL=http://127.0.0.1:8587/api\nOPENMETADATA_TOKEN='t-invented'\n")
    assert chain.catalog_env(env) == {"OPENMETADATA_URL": "http://127.0.0.1:8587/api", "OPENMETADATA_TOKEN": "t-invented"}


def test_a_catalog_that_hangs_is_cut_off_at_sixty_seconds_with_its_whole_process_group(monkeypatch):
    killed = []

    class Hung:
        pid = 4242

        def communicate(self, timeout=None):
            if timeout == 60:
                raise chain.subprocess.TimeoutExpired("x", 60)
            return ("", "")

    monkeypatch.setattr(chain.subprocess, "Popen", lambda *a, **k: Hung())
    monkeypatch.setattr(chain.os, "killpg", lambda pid, sig: killed.append(pid))
    assert chain.run_catalog_status(["x"], {})[0] == ""
    assert killed == [4242]  # the group, so no orphan keeps calling the catalog


def test_the_catalogs_private_file_is_found_by_the_variable_then_the_private_folder_then_the_checkout(tmp_path):
    home, root = tmp_path / "home", tmp_path / "repo"
    (home / ".config/edgartools").mkdir(parents=True)
    root.mkdir()
    (root / ".env").write_text("x=1\n")
    assert chain.catalog_env_file({}, home, root) == root / ".env"  # the legacy place
    private = home / ".config/edgartools/openmetadata.env"
    private.write_text("x=1\n")
    assert chain.catalog_env_file({}, home, root) == private  # the private folder outside any checkout comes first
    named = tmp_path / "elsewhere.env"
    named.write_text("x=1\n")
    assert chain.catalog_env_file({"OPENMETADATA_ENV_FILE": str(named)}, home, root) == named  # the operator's variable wins
    assert chain.catalog_env_file({"OPENMETADATA_ENV_FILE": str(tmp_path / "gone.env")}, home, root) == private  # a missing one is skipped


RUNS = [
    {"run_id": "r-old", "name": "sec.nport.security", "target": "silver", "state": "complete", "completed_at": "2026-11-18 11:00:00+00:00"},
    {"run_id": "r-new", "name": "sec.nport.security", "target": "silver", "state": "complete", "completed_at": "2026-11-18 13:00:00+00:00"},
    {"run_id": "r-other", "name": "sec.nport.security", "target": "mastering", "state": "complete", "completed_at": "2026-11-18 14:00:00+00:00"},
    {"run_id": "r-live", "name": "sec.nport.security", "target": "silver", "state": "running", "completed_at": None},
]


def test_the_latest_completed_run_of_a_source_and_target_comes_from_bookkeepings_own_rows():
    assert chain.latest_run(RUNS, "sec.nport.security", "silver") == "r-new"  # not the older one, not another target's, not a live one
    assert chain.latest_run(RUNS, "sec.nport.security", "mastering") == "r-other"
    assert chain.latest_run(RUNS, "gleif", "mastering") is None
    assert chain.latest_run([], "x", "y") is None


def test_a_step_with_no_run_in_any_log_falls_back_to_bookkeepings_latest_for_its_source_and_target(monkeypatch, tmp_path):
    monkeypatch.setattr(chain, "LOGS", tmp_path)
    monkeypatch.setattr(chain, "RUN", "fresh-v1")
    (tmp_path / "chain-fresh-v1-s1.log").write_text("Bundle 1/1: all 1 documents already loaded\n")
    monkeypatch.setattr(chain, "bookkeeping_runs", lambda: RUNS)
    step = {"name": "s1", "source": "sec.nport.security", "target": "silver"}
    assert chain.run_to_publish(step) == "r-new"
    (tmp_path / "chain-fresh-v1-s1.log").write_text(STEP_LOG)
    assert chain.run_to_publish(step) == "22222222-2222-4222-8222-222222222222"  # the log, when it names one, wins


def test_the_engine_is_the_executable_the_operator_names_else_uv(monkeypatch):
    assert chain.engine_command({"EDGAR_WAREHOUSE": "/x/venv/bin/edgar-warehouse"}) == ["/x/venv/bin/edgar-warehouse"]
    assert chain.engine_command({}) == ["uv", "run", "--no-sync", "edgar-warehouse"]


def test_an_answer_that_cannot_be_read_names_why_from_the_commands_last_error_line():
    assert chain.catalog_outcome("", "warning: x\nerror: Failed to spawn: edgar-warehouse\n  cause: No such file or directory") == \
        "not published: no readable answer (cause: No such file or directory)"
    assert chain.catalog_outcome("", "") == "not published: no readable answer"
    assert "postgresql://" not in chain.catalog_outcome("", "boom postgresql://u:pw@h/db")  # an address is hidden


def test_bookkeepings_runs_are_asked_for_within_the_commands_own_maximum_and_a_full_page_is_said_to_be_possibly_cut(monkeypatch):
    seen = {}

    def fake(command, env, timeout=60):
        seen["limit"] = int(command[command.index("--limit") + 1])
        return '[{"run_id": "r1"}]', ""

    monkeypatch.setattr(chain, "run_catalog_status", fake)
    monkeypatch.setattr(chain, "_RUNS", None)
    assert chain.bookkeeping_runs() == [{"run_id": "r1"}]
    assert seen["limit"] == chain.RUNS_LIMIT == 1000  # `bookkeeping runs` refuses more than 1000
    assert chain.runs_may_be_cut([{}] * 1000) and not chain.runs_may_be_cut([{}] * 999)


def test_a_missing_worker_env_means_no_bookkeeping_login_not_a_crash(monkeypatch, tmp_path):
    monkeypatch.setattr(chain, "STORES", tmp_path)  # a machine with no stores folder: CI, or a fresh checkout
    assert chain.worker_env() == {}
    (tmp_path / "worker.env").write_text("export DATA_URL='postgresql://b:p@h/data'\n")
    assert chain.worker_env() == {"DATA_URL": "postgresql://b:p@h/data"}
    monkeypatch.setattr(chain, "_RUNS", None)
    monkeypatch.setattr(chain, "run_catalog_status", lambda command, env, timeout=60: ("[]", ""))
    (tmp_path / "worker.env").unlink()
    assert chain.bookkeeping_runs() == []  # reads nothing, asks nothing it cannot, never raises


def test_a_load_does_not_build_the_name_search_lookups_and_they_are_built_only_when_asked(monkeypatch):
    """Nothing a load does reads them: only the context search does, and it refuses until they are built."""
    calls = []
    monkeypatch.setattr(chain, "run", lambda args, env, log=None: calls.append(args) or 0)
    monkeypatch.setattr(chain, "note", lambda message, state: None)
    chain.finish({}, Path("/dev/null"))
    assert ["mdm", "build-lookups"] not in calls and ["silver", "links"] in calls
    calls.clear()
    chain.finish({}, Path("/dev/null"), lookups=True)
    assert calls[0] == ["mdm", "build-lookups"]  # asked for: built first, then the links and master_binding
    assert ["silver", "links"] in calls


def test_lookups_are_refused_beside_a_partial_run_that_would_never_reach_them(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["load_jobs.py", "--lookups", "--lane", "A"])
    assert chain.main() == 2
    assert "--lookups" in capsys.readouterr().err


def test_a_file_made_while_the_generation_was_unreadable_learns_it_later_so_a_reset_is_still_caught(tmp_path):
    state = tmp_path / "chain.log"
    assert chain.ensure_store(state, "bbbb2222", generation="") == "fresh"  # a blip at creation: the marker names no generation
    state.write_text(state.read_text() + "11-18 06:40:00 ET company done: Done\n")
    assert chain.ensure_store(state, "bbbb2222", generation="2002") == "same"  # the next start can read it: the file learns it
    assert state.read_text().splitlines()[-1].endswith("chain store bbbb2222 generation 2002")
    assert chain.done_steps(state) == {"company"}
    assert chain.ensure_store(state, "bbbb2222", generation="3003") == "set aside"  # and a reset after that is caught
    assert chain.done_steps(state) == set()


def test_the_verdict_on_a_state_file_is_the_same_pure_answer_status_and_the_run_give():
    marked = "11-18 06:00:00 ET chain store aaaa1111 generation 7\n11-18 06:40:00 ET company done: Done\n"
    assert chain.state_verdict(marked, "aaaa1111", "7") == "same"
    assert chain.state_verdict(marked, "aaaa1111", "") == "same"  # unreadable: nothing is compared
    assert chain.state_verdict(marked, "aaaa1111", "8") == "set aside"  # databases made again
    assert chain.state_verdict(marked, "bbbb2222", "7") == "set aside"  # another store
    assert chain.state_verdict("11-18 06:40:00 ET company done: Done\n", "aaaa1111", "7") == "set aside"  # no marker
    assert chain.state_verdict("11-18 06:40:00 ET company done: Done\n", "aaaa1111", "7", adopt=True) == "adopted"
    assert chain.state_verdict("", "aaaa1111", "7") == "fresh"


def test_a_duty_files_data_database_names_the_store_and_a_file_without_one_names_none():
    assert chain.data_url({"DATA_URL": "postgresql+psycopg2://ops:pw@host.invalid:5432/data"}) == "postgresql://ops:pw@host.invalid:5432/data"
    assert chain.data_url({"CONTROL_URL": "postgresql://ops:pw@host.invalid:5432/control"}) is None


def test_full_swap_with_memory_to_spare_is_not_pressure_and_a_short_memory_is():
    """Swap used is a stock: macOS keeps it long after the pages that filled it are gone, so it cannot say the machine is pressed
    now. A scheduler that read it alone started nothing for a load it had just restarted (swap 85%, memory 56% free)."""
    assert chain.pressure(load=2.0, cores=8, swap_used=0.85, memory_free=0.56) == "low"  # room, so the workers may rise
    assert chain.pressure(load=2.0, cores=8, swap_used=0.85, memory_free=0.20) == "high"  # swap and little memory
    assert chain.pressure(load=2.0, cores=8, swap_used=0.10, memory_free=0.05) == "high"  # almost no memory, whatever the swap
    assert chain.pressure(load=2.0, cores=8, swap_used=0.85, memory_free=None) == "high"  # memory unreadable: the swap rule stands
    assert chain.memory_free_fraction("System-wide memory free percentage: 56%\n") == 0.56
    assert chain.memory_free_fraction("nothing here") is None


def test_the_memory_edges_of_pressure():
    assert chain.pressure(2.0, 8, 0.85, memory_free=0.25) == "ok"  # a quarter free: swap no longer presses, but there is no room to grow
    assert chain.pressure(2.0, 8, 0.85, memory_free=0.24) == "high"
    assert chain.pressure(2.0, 8, 0.10, memory_free=0.10) == "low"  # a tenth free is not yet short enough to press alone
    assert chain.pressure(2.0, 8, 0.10, memory_free=0.09) == "high"
    assert chain.pressure(2.0, 8, 0.60, memory_free=0.40) == "low"  # four tenths free is room whatever the swap
    assert chain.pressure(2.0, 8, 0.60, memory_free=0.39) == "ok"
    assert chain.pressure(2.0, 8, 0.76, memory_free=None) == "high"  # unreadable memory counts as short
    assert chain.pressure(13.0, 8, 0.95, relaxed=True, memory_free=0.5) == "ok"  # behind: the relaxed load limit still holds


def test_a_running_step_is_moved_at_most_once_in_ten_minutes_however_the_pressure_swings(monkeypatch, tmp_path):
    """Each move stops the step's load and starts it again, abandoning the bundles in flight and paying a start: the second
    hosted load moved IPO between 1 and 2 workers five times in twenty minutes as the load average crossed a line."""
    steps = [_step("a1", "A", minutes=600)]
    steps[0]["workers"] = 1
    state, started, killed, now = _timed(monkeypatch, tmp_path, steps, ticks=1, cycles=25)
    _paced(monkeypatch, started, now, per_worker=0.5)
    swings = iter(["low", "high"] * 40)
    monkeypatch.setattr(chain, "machine_pressure", lambda relaxed=False: next(swings))
    _run_auto(steps, state, slots=2)
    assert len(started) - 1 <= 2  # a swing that does not last sheds nothing; a raise waits for a bundle boundary and ten minutes


def test_a_pressed_machine_sheds_the_step_with_the_shortest_chain_even_when_it_moved_lately(monkeypatch, tmp_path):
    monkeypatch.setattr(chain, "step_log_text", lambda name: LOG)  # many bundles: a move loses only those in flight
    steps = [_step("long", "A", minutes=600), _step("short", "B", minutes=60)]
    for step in steps:
        step["workers"] = 8
    state, started, killed, now = _timed(monkeypatch, tmp_path, steps, ticks=5, cycles=6)
    levels = iter(["ok", "ok", "high", "high", "high", "high"])
    monkeypatch.setattr(chain, "machine_pressure", lambda relaxed=False: next(levels, "high"))
    _run_auto(steps, state, slots=2)
    moves = [move for move in started[2:]]
    assert moves[:2] == [("short", 4), ("short", 2)]  # the second shed lands on the same step: its last move does not shield it


def test_a_higher_priority_step_starts_before_one_with_a_longer_chain_behind_it():
    steps = [_step("long", "A", minutes=500), _step("tail", "A", minutes=500), _step("urgent", "B", minutes=5)]
    steps[2]["priority"] = 1
    assert chain.ready(steps, done=set(), running=set(), failed=set(), free=1) == ["urgent"]  # priority first, the chain second
    steps[2]["priority"] = 3
    assert chain.ready(steps, done=set(), running=set(), failed=set(), free=1) == ["long"]  # equal priority: the longest chain


def test_every_step_has_a_priority_of_one_two_or_three_and_the_chain_file_refuses_any_other(tmp_path):
    assert {step["priority"] for step in STEPS} <= {1, 2, 3}
    text = (ROOT / "rules" / "load-jobs.yaml").read_text()
    for bad in ("4", "true", "2.0"):
        other = tmp_path / "load-jobs.yaml"
        other.write_text(text.replace("bundles: 1, priority: 3,", "bundles: 1, priority: " + bad + ","))
        with pytest.raises(ValueError, match="priority"):
            chain.load_jobs(other)


def test_a_step_that_says_no_priority_is_three_and_starts_after_a_priority_two():
    steps = [_step("plain", "A", minutes=500), _step("second", "B", minutes=5)]
    steps[1]["priority"] = 2
    assert "priority" not in steps[0]
    assert chain.ready(steps, done=set(), running=set(), failed=set(), free=1) == ["second"]


def test_no_step_waits_on_one_of_a_lower_priority_than_the_step_that_follows_it():
    """A step that holds a higher tier behind it is at least that urgent itself: the priorities come from the chain behind a step."""
    follows = chain.needs(STEPS)
    for name, before in follows.items():
        for earlier in before:
            assert BY_NAME[earlier]["priority"] <= BY_NAME[name]["priority"], (earlier, name)


def test_the_runbook_names_exactly_the_steps_the_chain_file_gives_priority_one_and_two():
    section = (ROOT / "docs/runbooks/edgar-intelligence/init.md").read_text().split("## Load priority", 1)[1].split("\n## ", 1)[0]
    listed = {}
    for line in section.splitlines():
        row = re.match(r"\|\s*([12])\s*\|(.*?)\|", line)
        if row:
            listed[int(row.group(1))] = set(re.findall(r"`([a-z0-9-]+)`", row.group(2)))
    assert listed == {tier: {s["name"] for s in STEPS if s["priority"] == tier} for tier in (1, 2)}
    assert "Every other step is priority 3" in section


def test_a_marker_with_no_generation_is_from_before_generations_and_does_not_survive_a_reset():
    """A store made again inherited 59 done steps from a file whose marker named no generation, and the run ended at once."""
    legacy = "11-18 06:00:00 ET chain store aaaa1111\n11-18 06:40:00 ET company done: Done\n"
    assert chain.state_verdict(legacy, "aaaa1111", "7") == "set aside"
    assert chain.state_verdict(legacy, "aaaa1111", "") == "same"  # nothing readable to compare: nothing is thrown away
    marked_unread = "11-18 06:00:00 ET chain store aaaa1111 generation ?\n11-18 06:40:00 ET company done: Done\n"
    assert chain.state_verdict(marked_unread, "aaaa1111", "7") == "same"  # a blip at creation still learns it


def test_a_file_set_aside_for_a_missing_generation_is_kept_and_its_done_steps_count_for_nothing(tmp_path):
    state = tmp_path / "chain.log"
    state.write_text("11-18 06:00:00 ET chain store bbbb2222\n11-18 06:40:00 ET company done: Done\n")
    assert chain.ensure_store(state, "bbbb2222", generation="9") == "set aside"
    assert chain.done_steps(state) == set()
    assert [p.name for p in tmp_path.glob("chain.log.*") if not p.name.endswith(".lock")] == ["chain.log.bbbb2222-"]


def test_a_step_with_one_bundle_or_none_named_yet_is_never_moved(monkeypatch, tmp_path):
    """Two single-document steps were stopped and started again ten times as the machine's load moved, each time losing the whole
    attempt; they never finished."""
    one = "gleif mastering: 1 documents in 1 bundles\nBundle 1/1: 1 of 1 documents to load\n"
    for text in (one, ""):
        monkeypatch.setattr(chain, "step_log_text", lambda name, text=text: text)
        steps = [_step("a1", "A", minutes=600)]
        steps[0]["workers"] = 2
        state, started, killed, now = _timed(monkeypatch, tmp_path, steps, ticks=10)
        levels = iter(["ok", "low", "low", "low", "high", "high", "low", "low", "high", "ok"])
        monkeypatch.setattr(chain, "machine_pressure", lambda relaxed=False: next(levels, "ok"))
        _run_auto(steps, state, slots=2, deadline=now["t"] + chain.timedelta(minutes=90))
        assert [workers for _, workers in started] == [2] and killed == []


def test_only_a_log_naming_more_than_one_bundle_can_be_moved():
    assert chain.movable(LOG)
    assert not chain.movable("gleif mastering: 1 documents in 1 bundles\nBundle 1/1: 1 of 1 documents to load\n")
    assert not chain.movable("")


def test_a_verdict_has_one_kind_the_words_follow():
    busy = dict(log_age=2.0, cpu=40.0, lock_waiters=0)
    assert chain.verdict_kind(**busy) == "progressing"
    assert chain.verdict_kind(**{**busy, "log_age": 30.0, "cpu": 0.0}) == "stalled"
    assert chain.verdict_kind(**{**busy, "lock_waiters": 3}) == "progressing"  # waiters elsewhere on the store are no evidence of its own
    assert chain.verdict_kind(**{**busy, "lock_waiters": 3}, evidence=LOCK_WAITING) == "locked"
    assert chain.verdict_kind(**{**busy, "lock_waiters": 2}, evidence=LOCK_WAITING) == "progressing"  # one or two waiters are normal


def test_a_snapshot_names_the_state_of_every_step_and_what_a_waiting_step_waits_for(tmp_path, monkeypatch):
    steps = [{"name": "a1", "lane": "A", "source": "s1", "target": "mastering", "minutes": 60, "attempts": 2, "workers": 1},
             {"name": "b1", "lane": "B", "source": "s2", "target": "mastering", "minutes": 60, "attempts": 2, "workers": 1,
              "waits_for": ["a1"]},
             {"name": "c1", "lane": "C", "source": "s3", "target": "mastering", "minutes": 60, "attempts": 2, "workers": 1}]
    state = tmp_path / "state.log"
    state.write_text("11-23 07:00:00 ET a1 attempt 1 start\n11-23 07:10:00 ET a1 done: 5 min\n"
                     "11-23 07:11:00 ET c1 attempt 2 start\n")
    monkeypatch.setattr(chain, "external_loads", lambda: {("s3", "mastering")})
    monkeypatch.setattr(chain, "process_use", lambda source, target: ({1: 1.0}, 120.0))
    monkeypatch.setattr(chain, "machine_reading", lambda: {"load": 1.0, "cores": 8, "memory_free": 0.2})
    monkeypatch.setattr(chain, "database_load", lambda url: {"lock_waiters": 0})
    monkeypatch.setattr(chain, "database_sessions", lambda url: {})
    monkeypatch.setattr(chain, "step_sessions", lambda url: {"c1": {"active": 1, "idle_in_transaction": 0, "changed_min": 0.1,
                                                                    "statement": "insert mdm.mastering_record", "wait": "IO:DataFileRead"}})
    monkeypatch.setattr(chain, "database_writes", lambda url: {"mdm": 0})
    monkeypatch.setattr(chain, "writes_per_minute", lambda before, after, sample: {"mdm": 900.0})
    monkeypatch.setattr(chain, "LOGS", tmp_path)
    monkeypatch.setattr(chain.time, "sleep", lambda s: None)
    snap = chain.status_snapshot(steps, state, "postgresql://x/y", sample=1)
    assert {s["name"]: s["state"] for s in snap["steps"]} == {"a1": "done", "b1": "waiting", "c1": "progressing"}
    assert next(s for s in snap["steps"] if s["name"] == "b1")["waits_for"] == ["a1"]
    (row,) = snap["running"]
    assert (row["name"], row["attempt"], row["store"], row["rows_per_min"]) == ("c1", 2, "mdm", 900.0)
    assert (snap["done"], snap["total"], snap["machine"]["memory_free"]) == (1, 3, 0.2)
    assert "c1 (lane C, attempt 2" in "\n".join(chain.status_lines(snap))  # the text is the snapshot written out


def test_a_step_the_scheduler_gave_up_on_is_failed_until_it_starts_again(tmp_path):
    state = tmp_path / "state.log"
    state.write_text("11-23 07:00:00 ET a1 attempt 1 start\n11-23 07:01:00 ET a1 attempt 1 stopped rc=1: boom\n"
                     "11-23 07:02:00 ET a1 stopped: the same failure came back\n"
                     "11-23 07:03:00 ET b1 attempt 1 start\n11-23 07:04:00 ET b1 stopped: the same failure came back\n"
                     "11-23 07:05:00 ET b1 attempt 1 start\n")
    assert chain.failed_steps(state) == {"a1"}  # an attempt's own stop is not the scheduler giving up; b1 started again


def test_status_uses_the_explicit_run_label(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(chain, "LOGS", tmp_path)
    monkeypatch.setattr(chain, "STORES", tmp_path)
    monkeypatch.setattr(chain, "RUN", "fresh-v1")
    monkeypatch.setattr(chain, "external_loads", lambda: set())
    (tmp_path / "chain-after-clear.log").write_text("11-25 13:00:00 ET company done: loaded\n")
    monkeypatch.setattr(sys, "argv", ["load_jobs.py", "--status", "--json", "--run", "after-clear"])

    assert chain.main() == 0
    report = json.loads(capsys.readouterr().out)
    assert report["run"] == "after-clear"
    assert report["done"] == 1
    assert next(step for step in report["steps"] if step["name"] == "company")["state"] == "done"


def test_finish_records_how_long_it_took_against_its_bound(monkeypatch):
    notes = []
    monkeypatch.setattr(chain, "run", lambda args, env, log=None: 0)
    monkeypatch.setattr(chain, "note", lambda message, state: notes.append(message))
    chain.finish({}, Path("/dev/null"))
    assert any(m.startswith("finish took ") and "min" in m for m in notes) and notes[-1] == "chain done"


def test_a_running_steps_minutes_are_read_from_the_state_file_so_a_scheduler_restart_does_not_reset_them():
    text = ("11-23 10:00:00 ET company attempt 1 start\n11-23 11:00:00 ET gleif attempt 1 start\n"
            "11-23 11:30:00 ET gleif attempt 2 start\n11-23 11:45:00 ET person attempt 1 start\n")
    now = chain.datetime(2026, 11, 23, 12, 0, tzinfo=chain.ZoneInfo("America/New_York"))
    used = chain.minutes_running(text, {"gleif", "person", "never-started"}, now)
    assert used == {"gleif": 60.0, "person": 15.0}  # from the first attempt's start, none for a step with no start line


SESSION_ROWS = [  # (application_name, state, wait_event_type, wait_event, seconds since its last state change, statement)
    ("chain-nport-security-silver", "active", "IO", "DataFileRead", 2.0, "INSERT INTO silver.nport_holding (a, b) VALUES (1, 2)"),
    ("chain-nport-security-silver", "idle in transaction", "Client", "ClientRead", 30.0, "SELECT x FROM silver.nport_holding WHERE y = 3"),
    ("chain-company-facts", "idle in transaction", "Client", "ClientRead", 1500.0, "update silver.company_fact set a = 1"),
    ("", "active", None, None, 1.0, "select 1"),  # a session no step owns
]


def test_the_sessions_of_each_step_are_read_from_their_tag_and_a_statement_is_named_by_its_verb_and_table_only():
    found = chain.summarize_sessions(SESSION_ROWS)
    assert set(found) == {"nport-security-silver", "company-facts"}
    mine = found["nport-security-silver"]
    assert (mine["active"], mine["idle_in_transaction"]) == (1, 1) and mine["changed_min"] == pytest.approx(2 / 60)
    assert mine["statement"] == "insert silver.nport_holding" and mine["wait"] == "IO:DataFileRead"
    assert "1" not in mine["statement"] and "VALUES" not in mine["statement"]  # never a value
    assert found["company-facts"]["changed_min"] == 25.0


def test_a_step_with_a_working_session_is_progressing_at_no_cpu_and_never_unclear():
    quiet = dict(log_age=120.0, cpu=0.0, lock_waiters=0)
    working = {"active": 1, "idle_in_transaction": 0, "lock_waiting": 0, "changed_min": 0.03, "statement": "insert silver.t", "wait": "IO:DataFileRead"}
    waiting = {"active": 0, "idle_in_transaction": 1, "changed_min": 25.0, "statement": "update silver.t", "wait": "Client:ClientRead"}
    assert chain.verdict_kind(**quiet, evidence=working) == "progressing"  # the work is the database's
    assert chain.verdict_kind(**quiet, evidence=waiting) == "stalled"  # idle in a transaction for 25 minutes
    assert chain.verdict_kind(**quiet, evidence=None) == "stalled"
    assert chain.verdict_kind(**{**quiet, "cpu": 40.0}, evidence=waiting) == "progressing"
    assert chain.verdict_kind(**{**quiet, "lock_waiters": 3}, evidence=working) == "progressing"  # its sessions work: the waiters are others'
    assert chain.verdict_kind(**{**quiet, "lock_waiters": 3}, evidence=None) == "stalled"  # no session of its own waits on a lock
    assert chain.verdict_kind(**{**quiet, "lock_waiters": 3}, evidence=LOCK_WAITING) == "locked"


@pytest.mark.parametrize("evidence, key_words", [
    ({"active": 1, "idle_in_transaction": 0, "changed_min": 0.03, "statement": "insert silver.t", "wait": "IO:DataFileRead"}, "disk"),
    ({"active": 0, "idle_in_transaction": 1, "changed_min": 25.0, "statement": "update silver.t", "wait": "Client:ClientRead"}, "client"),
    ({"active": 1, "idle_in_transaction": 0, "changed_min": 0.1, "statement": "update silver.t", "wait": "Lock:transactionid"}, "lock"),
    (None, "no database session"),
])
def test_every_verdict_comes_with_five_whys_and_the_fifth_names_a_cause_or_what_was_not_measured(evidence, key_words):
    why = chain.five_whys(name="s", kind="stalled", elapsed=90.0, bound=60, log_age=45.0, cpu=0.0, evidence=evidence)
    assert len(why) == 5 and key_words in " ".join(why).lower()
    assert all("unclear" not in line.lower() for line in why)


def test_a_loads_database_sessions_carry_the_step_name_as_their_application_name(monkeypatch):
    monkeypatch.delenv("PGAPPNAME", raising=False)
    assert chain.application_name("gleif") == "chain-gleif"


def test_a_plan_of_one_step_or_lane_plans_only_it(monkeypatch, tmp_path):
    """A plan of every step took over five minutes to answer for one."""
    from tests.support.patching import checked

    (tmp_path / "worker.env").write_text("")
    monkeypatch.setattr(chain, "STORES", tmp_path)
    monkeypatch.setattr(chain, "LOGS", tmp_path)
    checked(monkeypatch, chain.subprocess, "Popen", lambda *a, **k: None)  # the wake lock
    planned = []
    checked(monkeypatch, chain, "plan", lambda step, env: planned.append(step["name"]) or "")
    monkeypatch.setattr(sys, "argv", ["load_jobs.py", "--plan", "--only", "company"])
    assert chain.main() == 0 and planned == ["company"]
    planned.clear()
    monkeypatch.setattr(sys, "argv", ["load_jobs.py", "--plan", "--lane", "A"])
    assert chain.main() == 0 and planned == [s["name"] for s in STEPS if s["lane"] == "A"]


def test_a_plan_names_the_open_runs_a_load_would_finish_and_those_it_would_leave(monkeypatch):
    from tests.support.patching import checked

    body = '{"documents": 7, "bundles": 2, "blocked": null, "finishable_runs": ["a", "b"], "left_as_they_are": {"c": "why"}}'
    checked(monkeypatch, chain.subprocess, "run", lambda *a, **k: type("R", (), {"stdout": body, "stderr": ""})())
    assert chain.plan(BY_NAME["company"], {}) == "documents 7 bundles 2 blocked None open runs: 2 to finish first, 1 left"


@pytest.mark.parametrize("argv", [["--only", "company"], ["--finish"], ["--auto"]])
def test_a_load_started_from_a_checkout_is_refused_before_the_gate(monkeypatch, tmp_path, capsys, argv):
    """Operator: "we must not be run the next load from a worktree". Only the loader image, which carries the commit CI
    built it from, starts, resumes or finishes a load; a plan still reads from anywhere."""
    from tests.support.patching import checked

    (tmp_path / "worker.env").write_text("")
    monkeypatch.setattr(chain, "STORES", tmp_path)
    monkeypatch.setattr(chain, "LOGS", tmp_path)
    monkeypatch.syspath_prepend(str(ROOT / "skills/data-operations/scripts"))  # as the script finds it, beside itself
    import readiness

    checked(monkeypatch, readiness, "gate", lambda *a: pytest.fail("a checkout is refused before the gate"))
    monkeypatch.setattr(sys, "argv", ["load_jobs.py", *argv])
    assert chain.main() == 2
    assert "infra/load-pipeline/load.sh" in capsys.readouterr().err


def test_a_step_whose_needed_step_failed_in_another_lane_stops_at_once_and_never_waits(tmp_path, monkeypatch):
    """Lanes run at once in the pipeline: a step waiting on a failed step of another lane waited forever, holding its lane
    until the state machine's timeout. It stops, names what blocked it, and counts as failed for the steps after it."""
    state = tmp_path / "state.log"
    state.write_text("11-23 07:00:00 ET a1 attempt 1 start\n11-23 07:02:00 ET a1 stopped: the same failure came back\n")
    monkeypatch.setattr(chain.time, "sleep", lambda s: pytest.fail("a step blocked by a failed step never waits"))
    assert chain.wait_for(_step("b1", "B", waits=["a1"]), state, poll=0) == {"a1"}
    assert "b1 stopped: blocked by a1" in state.read_text() and chain.failed_steps(state) == {"a1", "b1"}


def test_a_step_out_of_attempts_counts_as_failed_for_the_steps_that_need_it(tmp_path):
    state = tmp_path / "state.log"
    chain.note("a1 attempt 1 start", state)
    chain.note(chain.out_of_attempts("a1", 1), state)
    assert chain.failed_steps(state) == {"a1"}


def test_a_lane_that_stops_marks_its_later_steps_failed_so_no_other_lane_waits_on_them(tmp_path, monkeypatch):
    from tests.support.patching import checked

    state = tmp_path / "state.log"
    steps = [_step("a1", "A"), _step("a2", "A"), _step("a3", "A"), _step("b1", "B")]
    ran = []
    checked(monkeypatch, chain, "attempt_loop", lambda step, env, state: ran.append(step["name"]) or step["name"] != "a2")
    assert chain.run_steps(steps, {}, state, lane="A") is False
    assert ran == ["a1", "a2"] and "a3 stopped: not started, its lane stopped at a2" in state.read_text()
    assert chain.failed_steps(state) == {"a3"}


def test_a_failure_of_an_earlier_load_does_not_stop_a_step_of_this_one(tmp_path):
    """A rerun reuses the run's state file: a step that failed before and is about to run again is no failure of this load."""
    state = tmp_path / "state.log"
    state.write_text("11-23 07:00:00 ET a1 attempt 1 start\n11-23 07:02:00 ET a1 stopped: the same failure came back\n")
    chain.begin_load(state)
    assert chain.failed_steps(state) == set()
    chain.note("a2 stopped: blocked by a1", state)
    assert chain.failed_steps(state) == {"a2"}


def test_a_named_step_whose_needed_step_is_not_done_stops_and_never_waits_for_a_step_not_in_its_run(tmp_path, monkeypatch):
    state = tmp_path / "state.log"
    state.write_text("")
    monkeypatch.setattr(chain.time, "sleep", lambda s: pytest.fail("a step named alone never waits on another"))
    assert chain.wait_for(_step("b1", "B", waits=["a1"]), state, poll=0, others_run=False) == {"a1"}
    assert "b1 stopped: blocked by a1" in state.read_text()


def test_a_lane_that_breaks_records_its_steps_not_done_as_stopped(tmp_path, monkeypatch):
    from tests.support.patching import checked

    state = tmp_path / "state.log"
    steps = [_step("a1", "A"), _step("a2", "A")]

    def broken(step, env, state):
        raise RuntimeError("the worker broke")
    checked(monkeypatch, chain, "attempt_loop", broken)
    with pytest.raises(RuntimeError):
        chain.run_steps(steps, {}, state, lane="A")
    assert chain.failed_steps(state) == {"a1", "a2"}


def test_a_load_whose_step_would_wait_on_what_cannot_come_is_refused_before_any_step_runs():
    """Measured: named steps ran six loads, then one waited on a step not in the run, and would have until its timeout.
    Every wait is checked before the first step: a needed step that does not exist, a later step of its own lane, or, for
    named steps, a step neither done nor earlier in the run."""
    steps = [_step("a1", "A"), _step("a2", "A"), _step("b1", "B", waits=["a2"]), _step("c1", "C", waits=["b1"])]
    assert chain.wait_problems(steps) == []
    assert chain.wait_problems(steps, named=["a1", "a2", "b1"]) == []
    assert chain.wait_problems(steps, named=["b1"], done={"a2"}) == []
    assert chain.wait_problems(steps, named=["a1", "c1"]) == ["c1 needs b1: not done, and not before it in this run"]
    assert chain.wait_problems(steps, named=["b1", "a2"]) == ["b1 needs a2: not done, and not before it in this run"]
    assert chain.wait_problems(steps, named=["x9"]) == ["x9: no such step"]
    ghost = [*steps, _step("d1", "D", waits=["nope"])]
    assert chain.wait_problems(ghost) == ["d1 needs nope: no such step"]
    deadlock = [_step("a1", "A", waits=["b1"]), _step("b1", "B", waits=["a2"]), _step("a2", "A")]
    assert chain.wait_problems(deadlock) == ["the lanes cannot finish: a1, a2, b1 wait on each other"]


def test_begin_refuses_a_load_with_a_wait_problem_and_marks_no_start(tmp_path, monkeypatch, capsys):
    state = tmp_path / "state.log"
    steps = [_step("a1", "A"), _step("b1", "B", waits=["a1"])]
    assert chain.begin(steps, state, named=["b1"]) == 2
    assert "b1 needs a1" in capsys.readouterr().err and not state.exists()
    assert chain.begin(steps, state, named=["a1", "b1"]) == 0 and chain.LOAD_BEGINS in state.read_text()
    state.unlink()
    assert chain.begin(steps, state, named=["a1", "b1"], plan=True) == 0 and not state.exists()  # a plan writes nothing


def test_a_step_this_load_runs_is_done_only_once_this_load_finishes_it(tmp_path):
    """A step done by an earlier load satisfies a step that needs it only when this load does not run it again: a step this
    load runs again (a changed rule) is done when this load says so, so nothing reads it before then."""
    state = tmp_path / "state.log"
    chain.note("a1 done: Done: 0 documents loaded", state)
    chain.note("b1 done: Done: 0 documents loaded", state)
    chain.begin_load(state, ["b1", "c1"])
    assert chain.done_steps(state) == {"a1"}  # b1 runs again in this load
    chain.note("b1 done: Done: 3 documents loaded", state)
    assert chain.done_steps(state) == {"a1", "b1"}
    chain.begin_load(state)  # every step
    assert chain.done_steps(state) == set()


def test_a_lane_whose_process_ended_without_its_notes_has_its_steps_recorded_stopped(tmp_path):
    """A lane killed by a signal writes nothing: the worker records its steps not done, so no other lane waits on them."""
    state = tmp_path / "state.log"
    steps = [_step("a1", "A"), _step("a2", "A"), _step("b1", "B")]
    chain.begin_load(state)
    chain.note("a1 done: Done: 1 documents loaded", state)
    chain.mark_lane_stopped(steps, state, "A")
    assert chain.failed_steps(state) == {"a2"}


def test_the_whole_chain_in_file_order_is_refused_when_a_step_waits_on_a_later_one(tmp_path, capsys):
    steps = [_step("a1", "A", waits=["b1"]), _step("b1", "B")]
    assert chain.wait_problems(steps, named=[s["name"] for s in steps]) == [
        "a1 needs b1: not done, and not before it in this run"]


def test_a_load_started_by_the_loader_image_is_read_from_its_command_line(monkeypatch):
    """In the image the command is `edgar-warehouse` written as a python one-liner, so no line holds `edgar-warehouse load `."""
    line = ("python -c import sys; from edgar_warehouse.cli import main; sys.exit(main()) "
            "load --source one --target mastering --workers 3 --capture /c")
    monkeypatch.setattr(chain.subprocess, "run", lambda *a, **k: type("R", (), {"stdout": line + "\n"})())
    assert chain.external_loads() == {("one", "mastering")}
    assert chain.load_workers(f"4 1 0:01 100 {line}", "one", "mastering") == 3

def _chain_with_sources(tmp_path, steps, inputs):
    """A load jobs file and a sources folder whose `<source>/inputs.yaml` hold the named deliveries."""
    (tmp_path / "chain.yaml").write_text(yaml.safe_dump({"capture_label": "l", "steps": steps}))
    for source, body in inputs.items():
        (tmp_path / "sources" / source).mkdir(parents=True)
        (tmp_path / "sources" / source / "inputs.yaml").write_text(yaml.safe_dump(body, sort_keys=False))
    return tmp_path / "chain.yaml", tmp_path / "sources"


def test_a_step_names_its_input_and_the_source_holds_the_folder_and_its_root(tmp_path):
    path, sources = _chain_with_sources(tmp_path, [
        {"name": "a", "source": "s", "target": "t", "input": "d2", "minutes": 1},
        {"name": "b", "source": "s", "target": "t", "input": "d1", "minutes": 1},
        {"name": "c", "source": "p", "target": "t", "minutes": 1}], {
        "s": {"inputs": {"d1": {"folder": "s/d1"}, "d2": {"folder": "s/d2", "root": "proving"}}},
        "p": {"inputs": {"only": {"folder": "p/only"}}}})
    got = {s["name"]: [(one["capture"], one.get("capture_root", "captures"), one["capture_run"]) for one in chain.loads(s)]
           for s in chain.load_jobs(path, sources)}
    assert got == {"a": [("s/d2", "proving", "l-a-d2")], "b": [("s/d1", "captures", "l-b-d1")], "c": [("p/only", "captures", "l-c-only")]}


def several(tmp_path):
    path, sources = _chain_with_sources(tmp_path, [
        {"name": "first", "source": "p", "target": "t", "minutes": 1},
        {"name": "a", "source": "s", "target": "t", "minutes": 5, "attempts": 2, "workers": 1, "bundles": 1}], {
        "s": {"inputs": {"d2": {"folder": "s/d2"}, "d1": {"folder": "s/d1", "capture_name": "old"}}},
        "p": {"inputs": {"only": {"folder": "p/only"}}}})
    return chain.load_jobs(path, sources)[1]


def test_a_step_loads_every_delivery_of_its_source_in_the_files_order_each_under_its_own_run_and_place(tmp_path):
    step = several(tmp_path)
    assert [(o["capture"], o["capture_run"], o["position"], o["minutes"]) for o in chain.loads(step)] == [
        ("s/d2", "l-a-d2", 1, 5), ("s/d1", "l-a-old", 2, 5)]
    assert step["minutes"] == 10  # the bound of the step is all its deliveries'


@pytest.mark.parametrize("codes, ran, code, done", [
    ([0, 0], ["l-a-d2", "l-a-old"], 0, "Done: 2 documents loaded, 4 already loaded before, in 2 deliveries"),
    ([1], ["l-a-d2"], 1, "Done: 1 documents loaded, 2 already loaded before")])
def test_a_step_runs_its_deliveries_in_one_log_and_stops_at_the_first_that_does_not_finish(tmp_path, monkeypatch, codes, ran, code, done):
    called = []

    def run(args, env, log, append=False):
        called.append(args[args.index("--capture-run") + 1])
        assert append
        with log.open("a") as handle:
            handle.write("Bundle 1/3: 1 of 1 documents to load\n  run x complete in 1 min\nDone: 1 documents loaded, 2 already loaded before\n")
        return codes[len(called) - 1]

    monkeypatch.setattr(chain, "run", run)
    got, text = chain.run_deliveries(several(tmp_path), {}, tmp_path / "log")
    assert (called, got, chain.done_line(text)) == (ran, code, done)
    assert chain.bundle_progress(text) == (1, 3)  # of the delivery it is at, never every delivery's against the last one's total


def test_a_revision_is_its_deliverys_never_the_steps(tmp_path):
    path, sources = _chain_with_sources(tmp_path, [{"name": "a", "source": "s", "target": "t", "minutes": 1, "revision": 1}],
                                        {"s": {"inputs": {"d1": {"folder": "s/d1"}, "d2": {"folder": "s/d2"}}}})
    with pytest.raises(ValueError, match="belongs to one file"):
        chain.load_jobs(path, sources)


def test_a_deliverys_facts_and_revision_are_its_own_beside_the_steps(tmp_path):
    path, sources = _chain_with_sources(tmp_path, [{"name": "a", "source": "s", "target": "t", "minutes": 1, "facts": {"mode": "default"}}],
                                        {"s": {"inputs": {"d1": {"folder": "s/d1", "facts": {"day": "x", "of another target": "y"}, "revision": 4}, "d2": {"folder": "s/d2"}}}})
    (sources / "s" / "source.yaml").write_text(yaml.safe_dump({"bookkeeping": {"targets": {"t": {"run": {"facts": ["day", "mode"]}}}}}))
    (step,) = chain.load_jobs(path, sources)
    assert [(one["facts"], one.get("revision")) for one in chain.loads(step)] == [({"mode": "default", "day": "x"}, 4), ({"mode": "default"}, None)]


def test_the_load_jobs_hold_nothing_of_one_file():
    """A file's date, count or revision is beside its folder in `inputs.yaml`; the load jobs hold only how a target is loaded."""
    body = yaml.safe_load((ROOT / "rules/load-jobs.yaml").read_text())
    assert [(s["name"], s.get("facts")) for s in body["steps"] if s.get("facts")] == [
        ("company", {"capture_run": "fresh-v1-company", "catalog_run": "fresh-v1-catalog", "load_mode": "default"})]
    assert not [s["name"] for s in body["steps"] if "revision" in s]


def test_no_step_or_input_of_the_load_jobs_names_a_date():
    """A load is decoupled from its file: a new month or quarter is a line of the source's inputs, never a new step."""
    dated = re.compile(r"(19|20)\d\d|q[1-4]\b|-\d\d$")
    assert [s["name"] for s in STEPS if dated.search(s["name"]) or dated.search(str(s.get("input", "")))] == []


def test_the_capture_runs_stay_as_the_store_was_loaded():
    """A capture run is an input of its records: a new one processes every file again."""
    runs = {one["capture_run"] for step in STEPS for one in chain.loads(step)}
    single = {"fresh-v1-" + step["name"] for step in STEPS if len(step["deliveries"]) == 1}
    assert single <= runs  # a delivery added beside one of these must not rename it: its `capture_name` is empty
    assert {"fresh-v1-ncen-fund-2025q4", "fresh-v1-ncen-fund-2026q3", "fresh-v1-adv-mastering-03", "fresh-v1-adv-silver-06",
            "fresh-v1-adv-funds-03", "fresh-v1-adv-fund-advisers-06", "fresh-v1-adv-custodians-06", "fresh-v1-gleif",
            "fresh-v1-openfigi-answers", "fresh-v1-openfigi-tickers"} <= runs


@pytest.mark.parametrize("step, inputs, words", [
    ({"input": "nope"}, {"d1": {"folder": "s/d1"}}, "no input"),
    ({}, {}, "names no input"),
    ({"input": "d1"}, {"d1": {"folder": "s/d1", "root": "elsewhere"}}, "root"),
    ({"input": "d1"}, {"d1": {"folder": "/abs/path"}}, "folder")])
def test_an_input_that_cannot_be_resolved_is_refused_by_name(tmp_path, step, inputs, words):
    path, sources = _chain_with_sources(tmp_path, [{"name": "a", "source": "s", "target": "t", "minutes": 1, **step}],
                                        {"s": {"inputs": inputs}})
    with pytest.raises(ValueError, match=words):
        chain.load_jobs(path, sources)


def test_the_chain_file_holds_no_capture_folder_and_every_source_holds_its_own_inputs():
    text = (ROOT / "rules/load-jobs.yaml").read_text()
    assert not re.search(r"^\s*capture(_root)?:", text, re.M)
    assert all((ROOT / "sources" / s["source"] / "inputs.yaml").exists() for s in STEPS)


def test_each_step_resolves_to_the_folder_its_source_names():
    """The answer of every step, written once while it agreed with the load jobs file as it was before inputs moved to the sources."""
    got = {name: [(one["capture"], one.get("capture_root", "captures")) for one in chain.loads(BY_NAME[name])] for name in BY_NAME}
    assert got == {
        'company': [('sec.submissions.company/all-76230', 'captures')],
        'nport-registrant': [('sec.nport-datasets/2026q2', 'captures')],
        'nport-fund': [('sec.nport-datasets/2026q2', 'captures')],
        'person': [('sec.submissions.company/all-76230', 'captures')],
        'openfigi-answers': [('openfigi/2026q2-nport', 'captures')],
        'openfigi-tickers': [('openfigi/form4-tickers-20261109', 'captures')],
        '13f-securities': [('sec.thirteenf.securities/p07-cohort', 'captures')],
        '13f-securities-silver': [('sec.thirteenf.securities/p07-cohort', 'captures')],
        'ncen-registrant': [('sec.ncen-datasets/2025q4', 'captures'), ('sec.ncen-datasets/2026q1', 'captures'), ('sec.ncen-datasets/2026q2', 'captures'), ('sec.ncen-datasets/2026q3', 'captures')],
        'ncen-adviser': [('sec.ncen-datasets/2025q4', 'captures'), ('sec.ncen-datasets/2026q1', 'captures'), ('sec.ncen-datasets/2026q2', 'captures'), ('sec.ncen-datasets/2026q3', 'captures')],
        'adv-mastering': [('iapd.adv/p07-2026-03', 'captures'), ('iapd.adv/p07-2026-06', 'captures')],
        'adv-silver': [('iapd.adv/p07-2026-03', 'captures'), ('iapd.adv/p07-2026-06', 'captures')],
        'adv-funds': [('iapd.adv/p07-2026-03', 'captures'), ('iapd.adv/p07-2026-06', 'captures')],
        'adv-fund-advisers': [('iapd.adv/p07-2026-03', 'captures'), ('iapd.adv/p07-2026-06', 'captures')],
        'ncen-fund': [('sec.ncen-datasets/2025q4', 'captures'), ('sec.ncen-datasets/2026q1', 'captures'), ('sec.ncen-datasets/2026q2', 'captures'), ('sec.ncen-datasets/2026q3', 'captures')],
        'nport-security': [('sec.nport-datasets/2026q2', 'captures')],
        'nport-security-other-keys': [('sec.nport-datasets/2026q2', 'captures')],
        'ncen-class': [('sec.ncen-datasets/2025q4', 'captures'), ('sec.ncen-datasets/2026q1', 'captures'), ('sec.ncen-datasets/2026q2', 'captures'), ('sec.ncen-datasets/2026q3', 'captures')],
        'nport-security-silver': [('sec.nport-datasets/2026q2', 'captures')],
        'gleif-pairs': [('gleif/20260911-1600-publisher', 'captures')],
        'gleif': [('gleif/20260911-1600-publisher', 'captures')],
        'adv-custodians': [('iapd.adv/p07-2026-03', 'captures'), ('iapd.adv/p07-2026-06', 'captures')],
        'ownership': [('sec.ownership/p07-cohort', 'captures')],
        'ownership-symbols': [('sec.ownership/p07-cohort', 'captures')],
        'ownership-silver': [('sec.ownership/p07-cohort', 'captures')],
        '13f-filings': [('sec.thirteenf.filings/p07-managers', 'captures')],
        'company-facts': [('company-facts/cohort-json', 'proving')],
        'registration': [('sec.registration/s1-f1-originals', 'captures')],
        'ipo': [('sec.submissions.company/all-76230', 'captures')],
        'prospectus': [('sec.prospectus/first-424b4', 'captures')],
    }


def test_the_load_jobs_are_named_load_jobs_everywhere_a_reader_looks():
    """What the load runs is its load jobs: no tracked file names the old `load chain` or speaks of its chain, file or steps (tickets keep
    their history; the `chain-<RUN>.log` state files and `chain store` / `chain done` lines keep theirs, since a store's state is read by them)."""
    import subprocess

    old = re.compile(r"load[-_ ]chain|chain_steps|chain file|chain steps?\b|the chain's|chain state|whole chain|runs the chain|chain ended|chain stops|jobs's")
    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split("\n")
    named = [name for name in tracked if name and not name.startswith((".scratch/", "crates/")) and name != "uv.lock"
             and name != "tests/unit/test_load_jobs.py" and (ROOT / name).is_file()
             and old.search((ROOT / name).read_text(errors="ignore"))]
    assert named == []


def test_a_forced_run_gives_every_load_force_publish_and_an_ordinary_run_gives_none(monkeypatch):
    step = {"name": "x", "source": "s", "target": "t", "capture": "a/b", "workers": 2, "bundles": 3, "minutes": 5, "capture_run": "l-x"}
    monkeypatch.delenv(chain.FORCE, raising=False)
    assert "--force" not in chain.arguments(step)
    monkeypatch.setenv(chain.FORCE, "2026-11-23T20:00:00Z")
    forced = chain.arguments(step)
    assert forced[-5:] == ["--force", "--as-of", "2026-11-23T20:00:00Z", "--revision", "20261123200000000"]
    assert chain.arguments(step) == forced  # an attempt that follows one stopped at its bound names the same run


def test_a_forced_load_is_named_by_a_time_in_the_form_the_engine_reads():
    """The engine names a forced run `<run>+force-<digits of its time>`: one time for all attempts, so an attempt stopped at its
    bound (`minutes`) carries on in the same run instead of starting a run of its own."""
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", chain.forced_at())


@pytest.mark.parametrize("flag", ["--finish", "--list", "--status", "--begin", "--plan"])
def test_force_is_refused_where_there_is_no_document_to_force(monkeypatch, capsys, flag):
    monkeypatch.setattr(sys, "argv", ["load_jobs.py", "--force", flag])
    monkeypatch.delenv(chain.FORCE, raising=False)
    assert chain.main() == 2
    assert "--force goes with loads" in capsys.readouterr().err


def test_a_forced_load_is_a_new_publication_with_a_revision_above_the_one_the_file_gives(monkeypatch):
    """The first forced load of a store stopped 3 of its first jobs with "Source native revision has contradictory publications":
    the run name changed under the revision the file (or the delivery's date) gave. A forced load gives one revision of its own."""
    step = {"name": "x", "source": "s", "target": "t", "capture": "a/b", "workers": 2, "bundles": 3, "minutes": 5,
            "capture_run": "l-x", "revision": 1}
    monkeypatch.delenv(chain.FORCE, raising=False)
    assert chain.arguments(step)[chain.arguments(step).index("--revision") + 1] == "1"
    monkeypatch.setenv(chain.FORCE, "2026-11-24T12:19:19Z")
    args = chain.arguments(step)
    assert args.count("--revision") == 1 and args[args.index("--revision") + 1] == "20261124121919000"


@pytest.mark.parametrize("capacity, widest, carried, lanes, limit", [("local", 2, 8, 4, "memory"), ("aws-large", 2, 8, 4, "vcpu"),
                                                                     ("aws-medium", 4, 4, 1, "vcpu"), ("aws-small", 1, 2, 1, "memory")])
def test_a_compute_carries_the_workers_a_step_is_sized_by_over_the_widest_first_step_lanes_at_once(monkeypatch, capacity, widest, carried, lanes, limit):
    monkeypatch.setattr(chain.os, "cpu_count", lambda: 8)
    monkeypatch.setattr(chain, "physical_gb", lambda: 8.0)  # `local` carries half of it: 4 GB, so 8 workers of half a gigabyte
    monkeypatch.setattr(chain, "in_container", lambda: False)
    steps = [{"name": "a1", "lane": "A", "workers": 2}, {"name": "a2", "lane": "A", "workers": 8},
             {"name": "b1", "lane": "B", "workers": widest}, {"name": "c1", "lane": "C", "workers": 1}]
    # the workers a compute carries are its memory in worker-sized shares, at most four to a vCPU (the range a step's workers follow);
    # a later step of a lane (a2) never counts: the widest first step is 2 (or 4 for aws-medium's b1), so lanes = carried // widest
    assert chain.lane_budget(steps, capacity) == {"lanes": lanes, "workers": carried, "limit": limit}
    assert chain.lanes_at_once(steps, capacity) == lanes


def test_every_lane_of_the_real_load_jobs_is_started_and_load_sh_sets_that_number_in_the_definition(capsys, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["load_jobs.py", "--lane-count"])
    assert chain.main() == 0 and int(capsys.readouterr().out) == len({step["lane"] for step in STEPS})
    script = (ROOT / "infra/load-pipeline/load.sh").read_text()
    assert "--lane-count" in script and 'MaxConcurrency = $n' in script


def test_each_job_of_a_forced_load_publishes_its_own_revision_so_a_sources_quarters_never_clash(monkeypatch):
    """A forced load stopped two N-CEN jobs with "contradictory publications": every job of the run
    carried one revision, and the second quarter of a source published other content under the first quarter's revision."""
    monkeypatch.setenv(chain.FORCE, "2026-11-24T12:19:19Z")
    first = {"name": "q4", "source": "s", "target": "t", "capture": "a/b", "workers": 2, "bundles": 1, "minutes": 5, "capture_run": "l-q4", "position": 11}
    second = {**first, "name": "q1", "capture_run": "l-q1", "position": 12}
    revisions = [a[a.index("--revision") + 1] for a in (chain.arguments(first), chain.arguments(second))]
    assert revisions == ["20261124121919011", "20261124121919012"] and revisions[0] < revisions[1]
    assert all(one["position"] == place for place, one in enumerate(one for step in chain.load_jobs() for one in chain.loads(step)))


def test_inside_the_loader_container_local_is_the_whole_memory_the_runtime_gives_and_the_measured_worker_size_sets_the_lanes(monkeypatch):
    """The first memory-aware budget halved the container's memory (`local` is half a machine) and gave 1 lane where 2 had run:
    inside a container the memory seen is the runtime's whole allotment. A measured worker of 0.4 GB, 3.9 GB: 9 workers, 2 lanes of 4."""
    monkeypatch.setattr(chain.os, "cpu_count", lambda: 8)
    monkeypatch.setattr(chain, "physical_gb", lambda: 3.9)
    steps = [{"name": "a1", "lane": "A", "workers": 4, "worker_gb": 0.4}, {"name": "b1", "lane": "B", "workers": 2, "worker_gb": 0.4}]
    monkeypatch.setattr(chain, "in_container", lambda: True)
    assert chain.lane_budget(steps, "local") == {"lanes": 2, "workers": 9, "limit": "memory"}
    monkeypatch.setattr(chain, "in_container", lambda: False)  # on the Mac itself half of it is the load's: 1.95 GB, 4 workers, 1 lane
    assert chain.lane_budget(steps, "local")["lanes"] == 1
    assert all(step["worker_gb"] == 0.4 for step in chain.load_jobs())  # the file's default is the measured size


def test_a_lane_of_a_load_that_named_its_steps_runs_only_those_and_a_load_that_named_none_runs_them_all(tmp_path, monkeypatch):
    """`--in-lanes` restarted a forced load, and every lane still ran its first steps again (company and person, a quarter of an hour
    each): the begin recorded the named steps, but the lane ran every step it owns."""
    from tests.support.patching import checked

    steps = [_step("a1", "A"), _step("a2", "A"), _step("a3", "A"), _step("b1", "B")]
    ran = []
    checked(monkeypatch, chain, "attempt_loop", lambda step, env, state: ran.append(step["name"]) or True)
    state = tmp_path / "named.log"
    chain.begin_load(state, ["a2", "b1"])
    assert chain.run_steps(steps, {}, state, lane="A") is True and ran == ["a2"]
    ran.clear()
    every = tmp_path / "every.log"
    chain.begin_load(every)
    assert chain.run_steps(steps, {}, every, lane="A") is True and ran == ["a1", "a2", "a3"]


def test_a_step_with_one_session_waiting_on_a_lock_among_sessions_waiting_on_the_client_is_locked():
    rows = [("chain-s", "active", "Lock", "transactionid", 5, "update silver.t set a = 1"),
            ("chain-s", "idle in transaction", "Client", "ClientRead", 5, "select 1 from silver.t"),
            ("chain-s", "idle in transaction", "Client", "ClientRead", 5, "select 1 from silver.t")]
    mine = chain.summarize_sessions(rows)["s"]
    assert mine["wait"] == "Client:ClientRead" and mine["lock_waiting"] == 1  # the commonest wait is not the one that locks
    assert chain.verdict_kind(log_age=120.0, cpu=0.0, lock_waiters=3, evidence=mine) == "locked"
    assert chain.verdict_kind(log_age=120.0, cpu=0.0, lock_waiters=2, evidence=mine) == "progressing"  # one or two waiters are normal


def gate(tmp_path, want=4, free=None, running=lambda: True, sleeps=None, **more):
    """`admit` with a memory reading from a list (one per look) and a sleep that records."""
    looks = iter(free if isinstance(free, list) else [free])
    return chain.admit(want, 0.4, tmp_path / "gate", free=lambda: next(looks), running=running,
                       sleep=lambda seconds: sleeps.append(seconds) if sleeps is not None else None, settle=0, **more)


def test_a_step_takes_its_declared_workers_when_the_memory_is_there_and_as_many_as_fit_when_it_is_not(tmp_path):
    assert gate(tmp_path, free=3.0) == 4  # 7 workers fit: the step's own four
    assert gate(tmp_path, free=1.3) == 3  # three at 0.4 GB
    assert gate(tmp_path, free=0.85) == 2  # two fit at 0.4 GB, and two is half of four
    assert gate(tmp_path, free=0.3, running=lambda: False) == 2  # nothing fits and nothing else runs: the floor, not fewer
    assert gate(tmp_path, want=1, free=0.1, running=lambda: False) == 1


def test_a_step_waits_for_the_memory_of_its_floor_while_other_loads_run_and_starts_at_its_floor_when_none_runs(tmp_path):
    waited = []
    assert gate(tmp_path, free=[0.3, 0.5, 2.0], sleeps=waited) == 4  # 0.8 GB is the floor of two workers
    assert waited == [chain.GATE_POLL_SECONDS] * 2
    waited.clear()
    assert gate(tmp_path, free=[0.1], running=lambda: False, sleeps=waited) == 2  # nothing runs: waiting would be forever
    assert waited == []


def test_a_container_with_no_memory_limit_to_read_gives_the_declared_workers_without_waiting(tmp_path):
    waited = []
    assert gate(tmp_path, free=None, sleeps=waited) == 4 and waited == []


def test_the_free_memory_is_the_cgroup_limit_less_the_use_but_not_the_file_cache_and_the_machines_when_it_has_no_limit(tmp_path):
    meminfo = tmp_path / "meminfo"
    meminfo.write_text(f"MemTotal: {4 * 2**20} kB\nMemAvailable: {3 * 2**19} kB\n")  # 1.5 GB
    (tmp_path / "memory.max").write_text(str(4 * 2**30))
    (tmp_path / "memory.current").write_text(str(3 * 2**30))
    (tmp_path / "memory.stat").write_text(f"anon 1\ninactive_file {2**29}\n")
    assert chain.free_gb(tmp_path, tmp_path / "no-meminfo") == 1.5  # 4 - 3 + 0.5
    (tmp_path / "memory.max").write_text("max\n")
    assert chain.free_gb(tmp_path, meminfo) == 1.5  # no limit on the container: what the machine has available
    assert chain.free_gb(tmp_path / "missing", tmp_path / "no-meminfo") is None


def test_the_next_step_is_admitted_only_after_the_first_has_settled(tmp_path):
    import threading
    import time as clock
    lock = tmp_path / "gate"
    chain.admit(4, 0.4, lock, free=lambda: 3.0, running=lambda: True, sleep=lambda s: None, settle=0.4)
    began, seen = clock.monotonic(), []
    second = threading.Thread(target=lambda: seen.append((chain.admit(4, 0.4, lock, free=lambda: 3.0, running=lambda: True,
                                                                      sleep=lambda s: None, settle=0), clock.monotonic() - began)))
    second.start()
    second.join(5)
    assert seen and seen[0][0] == 4 and seen[0][1] >= 0.3  # it came in once the first's window had passed


def test_a_read_that_fails_while_a_step_waits_does_not_keep_the_lock(tmp_path):
    def broken():
        raise OSError("unreadable")
    with pytest.raises(OSError):
        chain.admit(4, 0.4, tmp_path / "gate", free=broken, running=lambda: True, sleep=lambda s: None, settle=3600)
    assert gate(tmp_path, free=3.0) == 4  # the lock is free again


def test_a_step_says_once_that_it_waits_for_memory(tmp_path):
    said = []
    gate(tmp_path, free=[0.1, 0.1, 2.0], say=said.append)
    assert len(said) == 1 and said[0].startswith("waits for 0.8 GB of free memory (0.1 GB now)")


def test_a_load_of_another_lane_is_seen_by_its_command_line():
    import subprocess
    other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)", "edgar-warehouse load --source x --target y "])
    try:
        assert chain.load_running()
    finally:
        other.kill()
        other.wait()
