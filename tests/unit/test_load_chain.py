"""The load chain names every target a store loads, each with the facts its target declares."""
import importlib.util
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


def test_every_step_starts_at_two_workers_and_stays_at_most_eight():
    """The skill starts a load at 2 workers and scales a long load to 8."""
    counts = {step["name"]: step["workers"] for step in STEPS}
    assert min(counts.values()) == 2, counts
    assert max(counts.values()) <= 8, counts


def test_the_skill_names_eleven_lanes_and_the_two_to_eight_worker_scale():
    skill = (ROOT / "skills/data-operations/SKILL.md").read_text()
    runbook = (ROOT / "docs/runbooks/edgar-intelligence/init.md").read_text()
    assert "A P S C L O D F G N Q" in skill and "A P S C L O D F G N Q" in runbook
    assert "Start `--workers 2`" in skill
    assert "scales to 8" in skill


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


def test_workers_rise_two_four_eight_on_the_longest_chain_first_and_fall_from_the_shortest():
    priority = {"long": 900, "mid": 300, "short": 50}
    assert chain.rescale({"long": 2, "mid": 2, "short": 2}, priority, "low") == ("long", 4)
    assert chain.rescale({"long": 8, "mid": 2, "short": 2}, priority, "low") == ("mid", 4)
    assert chain.rescale({"long": 8, "mid": 8, "short": 8}, priority, "low") is None  # the ceiling is 8
    assert chain.rescale({"long": 8, "mid": 4, "short": 4}, priority, "high") == ("short", 2)
    assert chain.rescale({"long": 2, "mid": 2, "short": 2}, priority, "high") is None  # the floor is 2
    assert chain.rescale({"long": 4, "mid": 4, "short": 4}, priority, "ok") is None


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
