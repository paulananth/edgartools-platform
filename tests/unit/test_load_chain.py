"""The load chain names every target a store loads, each with the facts its target declares."""
import importlib.util
import sys
from pathlib import Path

import pytest
import yaml

from edgar_warehouse.rules import files

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("load_chain", ROOT / "skills/data-operations/scripts/load_chain.py")
chain = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(chain)
STEPS = chain.chain_steps()
INFER = importlib.util.spec_from_file_location("infer_dependencies", ROOT / "skills/data-operations/scripts/infer_dependencies.py")
infer = importlib.util.module_from_spec(INFER)
INFER.loader.exec_module(infer)
INFERRED = infer.infer()
BY_NAME = {step["name"]: step for step in STEPS}


def targets():
    """Each (source, target) that loads a capture; a target that only copies or fetches one is not loaded here."""
    return {(name, target): body for name in sorted(p.parent.name for p in (files.ROOT / "sources").glob("*/source.yaml"))
            for target, body in (files.source(name).get("bookkeeping", {}).get("targets") or {}).items()
            if not {step["operation"] for step in body["steps"]} & {"artifact.copy", "provider.capture"}}


def test_step_names_are_unique_and_each_names_a_target_that_loads():
    names = [step["name"] for step in STEPS]
    assert len(names) == len(set(names))
    assert {(s["source"], s["target"]) for s in STEPS} <= set(targets())


def test_every_target_that_loads_a_capture_is_in_the_chain():
    assert set(targets()) <= {(s["source"], s["target"]) for s in STEPS}


def test_each_step_gives_exactly_the_facts_its_target_declares_and_the_capture_does_not_state():
    """A fact the target does not declare is refused when the load starts, and so is one the capture states."""
    for step in STEPS:
        target = targets()[(step["source"], step["target"])]
        read = {(target.get("delivered") or {}).get("fact")}
        assert set(step.get("facts") or {}) == set((target.get("run") or {}).get("facts") or []) - read, step["name"]


def test_no_step_types_the_date_or_the_order_of_a_delivery_its_capture_states():
    for step in STEPS:
        if "delivered" in targets()[(step["source"], step["target"])]:
            assert "revision" not in step, step["name"]


def test_a_later_delivery_of_one_source_carries_the_next_revision():
    seen = {}
    for step in STEPS:
        key = (step["source"], step["capture"].split("/")[0])
        if "revision" in step:
            seen.setdefault(key, []).append((step["capture"], step["revision"]))
    for key, runs in seen.items():
        order = list(dict.fromkeys(runs))
        assert [r for _, r in order] == list(range(len(order))), key


def test_the_arguments_follow_the_step():
    step = {"name": "x", "source": "s", "target": "t", "capture": "a/b", "workers": 2, "bundles": 3, "minutes": 5,
            "revision": 1, "facts": {"run": "{run}-x"}}
    args = chain.arguments(step)
    assert args[:4] == ["--source", "s", "--target", "t"]
    assert args[args.index("--capture-run") + 1] == f"{chain.RUN}-x"
    assert args[args.index("--revision") + 1] == "1"
    assert args[args.index("--fact") + 1] == f"run={chain.RUN}-x"


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
    lanes = {}
    for step in STEPS:
        lanes.setdefault(step["lane"], []).append(step)
    done = set()
    while any(lanes.values()):
        ran = False
        for queue in lanes.values():
            if queue and set(queue[0].get("waits_for") or []) <= done:
                done.add(queue.pop(0)["name"])
                ran = True
        assert ran, f"stuck: {[q[0]['name'] for q in lanes.values() if q]}"


def test_the_chain_builds_the_links_table_once_after_the_loads_and_no_target_builds_it():
    builds = sorted(f"{s}/{t}" for (s, t), body in targets().items()
                    if any((x.get("input") or {}).get("keys", {}).get("build") == "links" for x in body["steps"]))
    assert builds == []
    assert all("--no-links" in chain.arguments(step) for step in STEPS)
    calls = []
    original = chain.run
    chain.run = lambda args, env, log=None: calls.append(args) or 0
    try:
        chain.finish({}, Path("/dev/null"))
    finally:
        chain.run = original
    assert calls.count(["silver", "links"]) == 1 and calls.index(["silver", "links"]) < calls.index(next(c for c in calls if c[1] == "refresh-ids"))


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


def steps_of(source, like=None):
    """The chain steps of one source that master (a target with a kind of its own). A step of a quarterly delivery needs
    only the same delivery's steps of another source that has one (the same capture folder name), else all of them."""
    found = [s for s in STEPS if s["source"] == source and INFERRED[key(s)]["kinds"]]
    same = [s for s in found if like and s["capture"].split("/")[-1] == like["capture"].split("/")[-1]]
    return [s["name"] for s in (same or found)]


def test_a_load_follows_the_sources_its_rules_prefer():
    for step in STEPS:
        item = INFERRED[key(step)]
        wanted = set(item["prefer_after"])
        for source in wanted - {step["source"]}:
            assert set(steps_of(source, step)) <= ancestors(step["name"]), (step["name"], source)


def test_every_wait_is_explained_by_what_the_rules_declare():
    for step in STEPS:
        item = INFERRED[key(step)]
        for waited in step.get("waits_for") or []:
            other = BY_NAME[waited]
            assert other["source"] in item["prefer_after"], (step["name"], waited)


def test_a_step_takes_the_chains_defaults_for_what_it_does_not_say(tmp_path):
    path = tmp_path / "chain.yaml"
    path.write_text(yaml.safe_dump({"defaults": {"workers": 2, "bundles": 1}, "steps": [
        {"name": "plain", "minutes": 60}, {"name": "sized", "minutes": 60, "workers": 8}]}))

    assert [(s["name"], s["workers"], s["bundles"]) for s in chain.chain_steps(path)] == [("plain", 2, 1), ("sized", 8, 1)]


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


def test_the_machine_has_headroom_only_below_the_load_and_swap_limits():
    swap = "total = 9216.00M  used = 5751.50M  free = 1416.50M  (encrypted)"
    assert chain.swap_fraction(swap) == 5751.5 / 9216
    assert chain.swap_fraction("not a reading") is None
    assert chain.has_headroom(load=5.0, cores=8, swap_used=0.62)
    assert not chain.has_headroom(load=13.0, cores=8, swap_used=0.2)  # more than 1.5 x the cores
    assert not chain.has_headroom(load=2.0, cores=8, swap_used=0.8)  # swap over 75%
    assert chain.has_headroom(load=2.0, cores=8, swap_used=None)  # no reading is no reason to wait



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


def _timed(monkeypatch, tmp_path, steps, ticks):
    """`auto` with children that never end by themselves and a clock that moves `ticks` minutes a cycle."""
    state = tmp_path / "state.log"
    started, killed = [], []
    now = {"t": chain.datetime(2026, 11, 18, 8, 0, tzinfo=chain.ZoneInfo("America/New_York"))}

    def popen(command, **_):
        child = _Live(command)
        started.append((command[command.index("--only") + 1], int(command[command.index("--workers") + 1])))
        return child

    def sleep(_):
        now["t"] += chain.timedelta(minutes=ticks)

    monkeypatch.setattr(chain.subprocess, "Popen", popen)
    monkeypatch.setattr(chain.os, "killpg", lambda pid, sig: killed.append(pid))
    monkeypatch.setattr(chain, "external_loads", lambda: set())
    monkeypatch.setattr(chain, "clock", lambda: now["t"])
    monkeypatch.setattr(chain.time, "sleep", sleep)
    monkeypatch.setattr(chain, "note", lambda message, path: None)
    return state, started, killed, now


def test_at_the_deadline_the_scheduler_stops_what_it_started_and_names_what_is_left(monkeypatch, tmp_path):
    steps = [_step("a1", "A", minutes=60), _step("a2", "A", minutes=60)]
    state, started, killed, now = _timed(monkeypatch, tmp_path, steps, ticks=30)
    monkeypatch.setattr(chain, "machine_pressure", lambda relaxed=False: "ok")
    deadline = now["t"] + chain.timedelta(minutes=90)
    assert chain.auto(steps, state, slots=2, deadline=deadline) == 2
    assert [name for name, _ in started] == ["a1"] and len(killed) == 1  # a1 ran to the deadline; a2 never began


def test_a_running_step_is_restarted_with_more_workers_when_the_machine_has_room(monkeypatch, tmp_path):
    steps = [_step("a1", "A", minutes=600)]
    steps[0]["workers"] = 2
    state, started, killed, now = _timed(monkeypatch, tmp_path, steps, ticks=10)
    levels = iter(["ok", "low", "low", "low", "ok", "ok", "ok", "ok", "ok", "ok"])
    monkeypatch.setattr(chain, "machine_pressure", lambda relaxed=False: next(levels, "ok"))
    chain.auto(steps, state, slots=2, deadline=now["t"] + chain.timedelta(minutes=90))
    assert [workers for _, workers in started][:3] == [2, 4, 8]  # doubled while there was room, stopping at 8
    assert len(killed) >= 2


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
    steps = [_step("a1", "A", minutes=600), _step("b1", "B", minutes=60)]
    for step in steps:
        step["workers"] = 8
    state, started, killed, now = _timed(monkeypatch, tmp_path, steps, ticks=10)
    monkeypatch.setattr(chain, "machine_pressure", lambda relaxed=False: "low")
    locking = {"active": 9, "connections": 30, "max_connections": 100, "lock_waiters": 5, "longest_wait": 90.0}
    quiet = {**locking, "lock_waiters": 0, "longest_wait": 0.0}
    readings = iter([quiet, quiet])  # both steps start while the store is quiet, then it locks
    monkeypatch.setattr(chain, "database_load", lambda reader_url: next(readings, locking))
    chain.auto(steps, state, slots=2, deadline=now["t"] + chain.timedelta(minutes=45), reader_url="x")
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


def test_a_step_is_progressing_waiting_on_locks_or_possibly_stalled_by_its_own_evidence():
    busy = {"elapsed": 30.0, "bound": 480, "log_age": 40.0, "cpu": 85.0, "writes_per_min": 12000.0, "lock_waiters": 0}
    assert chain.verdict(**busy).startswith("progressing")
    assert chain.verdict(**{**busy, "writes_per_min": 0.0, "cpu": 0.0}).startswith("no sign of work")  # silent log too
    assert chain.verdict(**{**busy, "writes_per_min": 0.0, "cpu": 0.0, "log_age": 2.0}).startswith("progressing")  # log moved
    assert chain.verdict(**{**busy, "lock_waiters": 3}).startswith("waiting on database locks")
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
    busy = {"elapsed": 30.0, "bound": 480, "log_age": 40.0, "cpu": 0.0, "writes_per_min": 0.0}
    assert chain.verdict(**busy, lock_waiters=1).startswith("no sign of work")  # one waiter is normal
    assert chain.verdict(**busy, lock_waiters=3).startswith("waiting on database locks")


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


def test_a_step_sharing_a_store_whose_own_processes_are_idle_is_unclear_not_progressing():
    shared = {"elapsed": 120.0, "bound": 480, "log_age": 120.0, "cpu": 0.0, "writes_per_min": 214000.0, "lock_waiters": 0}
    said = chain.verdict(**shared, shares_store=["gleif"])
    assert said.startswith("unclear: its own processes used no CPU") and "gleif" in said
    assert chain.verdict(**shared, shares_store=[]).startswith("progressing")  # alone, the writes are its own
    assert chain.verdict(**{**shared, "cpu": 40.0}, shares_store=["gleif"]).startswith("progressing")


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
    steps[0]["workers"] = 8  # the chain file asks for eight; a small task carries two
    state, started, killed, now = _timed(monkeypatch, tmp_path, steps, ticks=10)
    monkeypatch.setattr(chain, "machine_pressure", lambda relaxed=False: "ok")
    chain.auto(steps, state, slots=2, deadline=now["t"] + chain.timedelta(minutes=20), bounds=(1, 2))
    assert started[0] == ("a1", 2)


def test_a_started_step_is_told_the_capacity_it_runs_on_so_its_own_check_uses_the_same_range(monkeypatch, tmp_path):
    commands = []
    steps = [_step("a1", "A", minutes=600)]
    state, started, killed, now = _timed(monkeypatch, tmp_path, steps, ticks=10)
    original = chain.subprocess.Popen
    monkeypatch.setattr(chain.subprocess, "Popen", lambda command, **kw: commands.append(command) or original(command, **kw))
    monkeypatch.setattr(chain, "machine_pressure", lambda relaxed=False: "ok")
    chain.auto(steps, state, slots=2, deadline=now["t"] + chain.timedelta(minutes=20), bounds=(1, 4), capacity="aws-medium")
    assert commands[0][commands[0].index("--capacity") + 1] == "aws-medium"


def test_every_run_mode_holds_a_steps_workers_to_the_capacity_not_only_the_scheduler():
    steps = [{"name": "gleif", "workers": 8}, {"name": "small", "workers": 2}, {"name": "tiny", "workers": 1}]
    assert [s["workers"] for s in chain.clamped(steps, "local", capacity=(1, 4.0))] == [4, 2, 1]  # a medium task starts GLEIF at 4
    assert [s["workers"] for s in chain.clamped(steps, "local", capacity=(2, 8.0))] == [8, 2, 1]  # and a larger one at 8
    assert steps[0]["workers"] == 8  # the chain file's own steps are not changed


def test_a_state_file_from_another_store_is_set_aside_so_its_done_lines_never_satisfy_a_wait(tmp_path):
    state = tmp_path / "chain.log"
    state.write_text("11-15 14:21:31 ET chain store aaaa1111\n11-15 14:21:31 ET company done: Done\n")
    assert chain.ensure_store(state, "bbbb2222") == "set aside"  # a different store: the old lines are archived
    assert chain.done_steps(state) == set()
    assert state.read_text().endswith("chain store bbbb2222\n")
    assert (tmp_path / "chain.log.aaaa1111").read_text().count("company done") == 1
    state.write_text(state.read_text() + "11-18 06:40:00 ET company done: Done\n")
    assert chain.ensure_store(state, "bbbb2222") == "same"  # the same store: nothing is touched
    assert chain.done_steps(state) == {"company"}
    fresh = tmp_path / "new.log"
    assert chain.ensure_store(fresh, "bbbb2222") == "fresh" and fresh.read_text().endswith("chain store bbbb2222\n")


def test_a_state_file_with_lines_and_no_marker_is_set_aside_and_kept_never_trusted_and_never_a_reason_to_stop(tmp_path):
    """An old run's file under the same label (a hand-chosen name can repeat) must not stop a load or satisfy its waits."""
    state = tmp_path / "chain.log"
    state.write_text("11-15 14:21:31 ET company done: Done\n")
    assert chain.ensure_store(state, "bbbb2222") == "set aside"  # no marker: its done lines are not this store's to trust
    assert chain.done_steps(state) == set() and state.read_text().endswith("chain store bbbb2222\n")
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
    assert chain.ensure_store(older, "bbbb2222", generation="3003") == "same"  # nothing to compare: kept


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
    assert not chain.retry_is_pointless("", error)  # a first failure is always retried
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
    offset = log.stat().st_size
    log.write_text(log.read_text()
                   + "$ rules run --source sec.x --target mastering --work-run-id r\nValueError: postgresql://u:pw@h:5432/db failed\n"
                   + "$ mdm prepare-capture --source openfigi --target mastering --capture /c\nKeyError: another lane's block\n")
    kept = chain.errors_since(log, offset, "sec.x", "mastering")
    assert "ValueError" in kept and "OldError" not in kept and "another lane" not in kept
    assert "pw" not in kept and "<addr>" in kept
    assert "another lane" in chain.errors_since(log, offset)  # with no step named, every block since the offset
    assert chain.errors_since(tmp_path / "missing.log", 0, "sec.x", "mastering") == ""


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
        path.write_text(yaml.safe_dump({"defaults": {"workers": 2, "bundles": 1}, "steps": [
            {"name": "x", "minutes": 60, "worker_gb": bad}]}))
        with pytest.raises(ValueError, match="worker_gb"):
            chain.chain_steps(path)


def test_the_start_count_and_the_rescale_use_each_steps_own_measured_range(monkeypatch, tmp_path):
    steps = [_step("gleif", "A", minutes=600), _step("plain", "B", minutes=60)]
    steps[0].update(workers=16, worker_gb=0.4)
    steps[1].update(workers=16)
    monkeypatch.setattr(chain, "capacity_of", lambda name: (8, 4.0))  # 4 GB: GLEIF carries 10, a half-gigabyte worker 8
    state, started, killed, now = _timed(monkeypatch, tmp_path, steps, ticks=10)
    monkeypatch.setattr(chain, "machine_pressure", lambda relaxed=False: "ok")
    chain.auto(steps, state, slots=2, deadline=now["t"] + chain.timedelta(minutes=30))
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


def test_a_steps_catalog_status_is_published_after_it_finishes_and_a_failure_never_fails_the_step(monkeypatch, tmp_path):
    asked = []
    monkeypatch.setattr(chain, "publish_catalog_status", lambda step: asked.append(step["name"]) or "published to svc.t")
    steps = [_step("a1", "A")]
    state, started, killed, now = _timed(monkeypatch, tmp_path, steps, ticks=10)
    log = tmp_path / "log"
    log.write_text(STEP_LOG)
    notes = []
    monkeypatch.setattr(chain, "note", lambda message, path: notes.append(message))
    chain.after_done(steps[0], state)
    assert asked == ["a1"] and any("catalog status" in n and "published to svc.t" in n for n in notes)
    monkeypatch.setattr(chain, "publish_catalog_status", lambda step: (_ for _ in ()).throw(RuntimeError("boom")))
    chain.after_done(steps[0], state)  # raises nothing: the load is done whatever the catalog says
    assert any("not published" in n for n in notes)


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
    base = {"PATH": "/bin", "HOME": "/h", "AWS_SECRET_ACCESS_KEY": "no", "MDM_DATABASE_URL": "no", "OPENMETADATA_ADMIN_PASSWORD": "no"}
    worker = {"BOOKKEEPING_DATABASE_URL": "postgresql://b:p@h/x", "MDM_DATABASE_URL": "postgresql://m:p@h/y", "SILVER_DATABASE_URL": "no"}
    catalog = {"OPENMETADATA_URL": "http://127.0.0.1:8587/api", "OPENMETADATA_TOKEN": "t"}
    given = chain.status_env(base, worker, catalog)
    assert set(given) == {"PATH", "HOME", "BOOKKEEPING_DATABASE_URL", "OPENMETADATA_URL", "OPENMETADATA_TOKEN"}
    assert "no" not in given.values()  # no other login, key or password reaches it


def test_a_step_that_loaded_nothing_new_in_its_last_attempt_publishes_the_run_of_an_earlier_one(tmp_path, monkeypatch):
    monkeypatch.setattr(chain, "LOGS", tmp_path)
    monkeypatch.setattr(chain, "RUN", "fresh-v1")
    (tmp_path / "chain-fresh-v1-a1.log").write_text("Bundle 1/1: all 5 documents already loaded\nDone: 0 documents loaded, 5 already loaded before\n")
    (tmp_path / "chain-fresh-v1-a1.log.attempt-1").write_text(STEP_LOG.replace("22222222", "33333333"))
    (tmp_path / "chain-fresh-v1-a1.log.attempt-2").write_text(STEP_LOG)
    assert chain.step_run_id("a1") == "22222222-2222-4222-8222-222222222222"  # its newest attempt that ran one
    assert chain.step_run_id("none") is None


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
    (tmp_path / "worker.env").write_text("export BOOKKEEPING_DATABASE_URL='postgresql://b:p@h/x'\n")
    assert chain.worker_env() == {"BOOKKEEPING_DATABASE_URL": "postgresql://b:p@h/x"}
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
    assert calls[0] == ["mdm", "build-lookups"]  # asked for: built first, then the links and the master ids
    assert ["silver", "links"] in calls


def test_lookups_are_refused_beside_a_partial_run_that_would_never_reach_them(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["load_chain.py", "--lookups", "--lane", "A"])
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


def test_the_reader_reads_the_mdm_databases_generation_whatever_database_its_address_names():
    assert chain.mdm_url_of("postgresql+psycopg2://ops:pw@host.invalid:5432/bookkeeping") == "postgresql+psycopg2://ops:pw@host.invalid:5432/mdm"
