"""The load chain names every target a store loads, each with the facts its target declares."""
import importlib.util
from pathlib import Path

import yaml

from edgar_warehouse.rules import files

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("load_chain", ROOT / "skills/data-operations/scripts/load_chain.py")
chain = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(chain)
STEPS = yaml.safe_load((ROOT / "rules/load-chain.yaml").read_text())["steps"]
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


def test_each_step_gives_exactly_the_facts_its_target_declares():
    """A fact the target does not declare is refused when the load starts (a second-batch target took none)."""
    for step in STEPS:
        declared = set((targets()[(step["source"], step["target"])].get("run") or {}).get("facts") or [])
        assert set(step.get("facts") or {}) == declared, step["name"]


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


def test_the_chain_has_eight_lanes_and_company_facts_is_the_eighth():
    """A P S C L O D plus F: company-facts runs beside the other silver-only sources."""
    assert {step["lane"] for step in STEPS} == set("APSCLODF")
    assert {s["lane"] for s in STEPS if s["source"] == "sec.company-facts"} == {"F"}


def test_every_step_starts_at_two_workers_and_stays_at_most_eight():
    """The skill starts a load at 2 workers and scales a long load to 8."""
    counts = {step["name"]: step["workers"] for step in STEPS}
    assert min(counts.values()) == 2, counts
    assert max(counts.values()) <= 8, counts


def test_the_skill_names_eight_lanes_and_the_two_to_eight_worker_scale():
    skill = (ROOT / "skills/data-operations/SKILL.md").read_text()
    runbook = (ROOT / "skills/data-operations/RUNBOOK.md").read_text()
    assert "A P S C L O D F" in skill and "A P S C L O D F" in runbook
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


def test_a_target_that_reads_another_runs_step_follows_that_target():
    for step in STEPS:
        for after in INFERRED[key(step)]["after_target"]:
            earlier = [s["name"] for s in STEPS if s["source"] == step["source"] and s["target"] == after]
            assert earlier and set(earlier) <= ancestors(step["name"]), step["name"]


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
            explained = (other["source"] in item["prefer_after"]
                         or (other["source"] == step["source"] and other["target"] in item["after_target"]))
            assert explained, (step["name"], waited)
