"""The load monitor: design tokens, exporter metrics, the dashboard built from them and the compose refusal."""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills/load-monitoring/scripts"
sys.path.insert(0, str(SCRIPTS))
import dashboard  # noqa: E402
import design  # noqa: E402


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


exporter, monitoring = load("exporter"), load("monitoring")

SNAPSHOT = {
    "total": 3, "done": 1, "failed": 1, "writes": {"mdm": 900.0}, "lock_waiters": 1,
    "sessions": {"data": {"active": 2, "waiting_on_client": 5}},
    "machine": {"load": 4.0, "cores": 8, "memory_free": 0.2},
    "steps": [{"name": "a1", "lane": "A", "state": "done", "waits_for": []},
              {"name": 'b"1', "lane": "B", "state": "progressing", "waits_for": ["a1"]},
              {"name": "c1", "lane": "C", "state": "failed", "waits_for": []}],
    "running": [{"name": 'b"1', "lane": "B", "attempt": 2, "workers": 2, "elapsed": 14.0, "bound": 300, "log_age": 3.0,
                 "cpu": 40.0, "memory_mb": 210.0, "store": "mdm", "rows_per_min": 900.0,
                 "kind": "stalled", "why": ["a", "b", "c", "d", 'the store reads the table from disk ("cache misses")']}]}


def test_every_state_has_one_code_and_not_running_or_complete_is_grey_running_orange_done_green_the_rest_red():
    names, codes, colours = zip(*[(n, c, k) for n, c, k, _ in design.STATES])
    assert len(set(names)) == len(set(codes)) == 7
    assert dict(zip(names, colours)) == {"waiting": "#8b949e", "progressing": "#e16f24", "done": "#2da44e",
                                         "failed": "#cf222e", "stalled": "#cf222e", "locked": "#cf222e", "complete": "#8b949e"}
    # Prometheus keeps the codes it stored: dropping `unclear` leaves code 2 unused, and no other state is renumbered (history would repaint)
    assert sorted(codes) == [0, 1, 3, 4, 5, 6, 7] and "unclear" not in names


def test_once_the_load_is_complete_every_step_is_grey_and_the_done_count_stays():
    text = exporter.render({**SNAPSHOT, "complete": True})
    assert 'load_step_state{lane="A",step="a1"} 7' in text and 'load_step_state{lane="C",step="c1"} 7' in text
    assert "load_complete 1" in text and 'load_steps{state="done"} 1' in text
    running = exporter.render(SNAPSHOT)
    assert "load_complete 0" in running and 'load_step_state{lane="A",step="a1"} 5' in running


def test_the_exporter_writes_a_code_per_step_and_a_count_per_state_zeros_included():
    text = exporter.render(SNAPSHOT)
    assert 'load_step_state{lane="A",step="a1"} 5' in text and 'load_step_state{lane="C",step="c1"} 6' in text
    for state in design.CODE:
        assert f'load_steps{{state="{state}"}}' in text
    assert 'load_steps{state="stalled"} 0' in text and "load_machine_load_per_core 0.5" in text
    assert 'load_step_attempt{lane="B",step="b\\"1"} 2' in text  # a quote in a label is escaped


def test_a_step_that_waits_carries_what_it_waits_for():
    assert 'load_step_info{lane="B",step="b\\"1",state="progressing",waits_for="a1"} 1' in exporter.render(SNAPSHOT)


def test_a_failed_reading_is_a_down_metric_not_a_crash():
    assert exporter.down() == "load_monitor_up 0\n"


def test_every_panel_says_what_it_shows_and_the_ones_with_data_share_one_source():
    panels = dashboard.build()["panels"]
    assert all(len(p["description"]) > 40 for p in panels)
    assert len({p["title"] for p in panels}) == len(panels)
    assert {p["datasource"]["uid"] for p in panels} == {dashboard.SOURCE["uid"]}


def test_the_lane_board_maps_every_state_to_its_token_colour():
    (lanes,) = [p for p in dashboard.build()["panels"] if p["title"] == "Lanes"]
    mapped = lanes["fieldConfig"]["defaults"]["mappings"][0]["options"]
    assert {v["text"]: v["color"] for v in mapped.values()} == {n: c for n, _, c, _ in design.STATES}
    assert all(meaning in lanes["description"] for *_, meaning in design.STATES)


def test_thresholds_are_the_chains_own_limits():
    by_title = {p["title"]: p for p in dashboard.build()["panels"]}
    steps = lambda title: [s["value"] for s in by_title[title]["fieldConfig"]["defaults"]["thresholds"]["steps"]]
    assert steps("Lock waiters") == [None, *design.LOCK_WAITERS]
    assert steps("Memory free") == [None, *design.MEMORY_FREE]
    memory = [s["color"] for s in by_title["Memory free"]["fieldConfig"]["defaults"]["thresholds"]["steps"]]
    running = next(c for n, _, c, _ in design.STATES if n == "progressing")
    assert memory == ["#cf222e", "#d4a72c", "#2da44e"] and running not in memory
    log_age = next(o for o in by_title["Running now"]["fieldConfig"]["overrides"] if o["matcher"]["options"] == "Log age min")
    assert [s["value"] for s in log_age["properties"][0]["value"]["steps"]] == [None, *design.LOG_AGE_MINUTES]


def test_the_dashboard_is_code_in_eastern_time_with_restart_and_failure_marks():
    board = dashboard.build()
    assert board["editable"] is False and board["timezone"] == "America/New_York"
    assert {a["name"] for a in board["annotations"]["list"]} == {"Restarts", "Failures", "Load complete"}
    complete = next(a for a in board["annotations"]["list"] if a["name"] == "Load complete")
    assert "load_complete" in complete["expr"] and "{{step}}" not in complete["textFormat"]


def test_a_stale_or_checkout_bound_compose_file_is_refused():
    good = {"services": {"grafana": {"ports": [{"published": "3001"}]}, "prometheus": {"volumes": [{"type": "volume"}]}}}
    assert monitoring.problems_in(good) == []
    bad = {"services": {"grafana": {"ports": [{"published": "3000"}], "volumes": [{"type": "bind", "source": "/work/x"}]}}}
    assert len(monitoring.problems_in(bad)) == 2


def test_the_compose_file_mounts_nothing_from_the_checkout():
    text = (ROOT / "infra/monitoring/docker-compose.yml").read_text()
    assert "./" not in text.replace("# ", "") and "content: |" in text


def test_a_running_step_publishes_the_cause_its_five_whys_end_on_and_the_table_shows_it():
    text = exporter.render(SNAPSHOT)
    assert 'load_step_cause{lane="B",step="b\\"1",cause="the store reads the table from disk (\\"cache misses\\")"} 1' in text
    running = dashboard.running_table()
    assert any("load_step_cause" in t["expr"] for t in running["targets"])
    assert "Why" in str(running["transformations"])


def test_a_step_that_is_not_progressing_publishes_all_five_whys_and_a_panel_lists_them():
    text = exporter.render(SNAPSHOT)
    for number, words in enumerate(["a", "b", "c", "d"], 1):
        assert f'load_step_why{{lane="B",step="b\\"1",number="{number}",why="{words}"}} 1' in text
    healthy = {**SNAPSHOT, "running": [{**SNAPSHOT["running"][0], "kind": "progressing"}]}
    assert "load_step_why" not in exporter.render(healthy)  # a step that works has no whys to show
    panel = dashboard.whys_table()
    assert any("load_step_why" in t["expr"] for t in panel["targets"]) and "Because" in str(panel["transformations"])
    assert panel in dashboard.build()["panels"] and panel["description"]


def test_the_monitor_starts_no_host_exporter_while_the_pipelines_exporter_answers(monkeypatch):
    monkeypatch.setattr(monitoring, "exporter_pid", lambda: None)
    monkeypatch.setattr(monitoring, "exporter_answer", lambda: "up")
    monkeypatch.setattr(monitoring.subprocess, "Popen", lambda *a, **k: pytest.fail("a second exporter was started"))
    monitoring.start_exporter()


def test_the_monitor_starts_a_host_exporter_when_nothing_answers(monkeypatch, tmp_path):
    started = []
    monkeypatch.setattr(monitoring, "exporter_pid", lambda: None)
    monkeypatch.setattr(monitoring, "exporter_answer", lambda: "not answering")
    monkeypatch.setattr(monitoring, "STATE", tmp_path)
    monkeypatch.setattr(monitoring, "PID", tmp_path / "exporter.pid")
    monkeypatch.setenv("RUN", "after-clear")
    monkeypatch.setattr(monitoring.subprocess, "Popen", lambda argv, **k: started.append(argv) or type("P", (), {"pid": 1})())
    monitoring.start_exporter()
    assert len(started) == 1 and started[0][-3:] == ["serve", "--run", "after-clear"]


def test_monitor_passes_the_selected_run_to_standalone_exporter(monkeypatch):
    seen = []
    monkeypatch.setattr(sys, "argv", ["monitoring.py", "up", "--run", "after-clear"])
    monkeypatch.setattr(monitoring, "up", lambda run: seen.append(run) or 0)

    assert monitoring.main() == 0
    assert seen == ["after-clear"]


def test_exporter_passes_the_selected_run_to_load_status(monkeypatch):
    seen = []
    monkeypatch.setattr(sys, "argv", ["exporter.py", "serve", "--run", "after-clear"])
    monkeypatch.setattr(exporter, "serve", lambda port, interval, sample, run: seen.append(run))

    assert exporter.main() == 0
    assert seen == ["after-clear"]


def test_the_exporter_shows_the_worker_limit_and_what_sets_it_beside_the_workers_running():
    """The monitor and data-operations share one limit: the workers the load may hold, what sets it, and what runs against it."""
    text = exporter.render({**SNAPSHOT, "budget": {"workers": 8, "limit": "memory"}})
    assert 'load_worker_budget{limit="memory"} 8' in text and "load_workers_running 2" in text
    assert "load_worker_budget" not in exporter.render(SNAPSHOT)  # a reading with no budget shows none, never a guess


def selected(link_url: str) -> str:
    from urllib.parse import parse_qs, urlparse
    return parse_qs(urlparse(link_url).query)["var-state"][0]


def test_a_tile_click_filters_the_lanes_to_the_states_it_counts():
    import re
    board = dashboard.build()
    by_title = {p["title"]: p for p in board["panels"]}
    (variable,) = [v for v in board["templating"]["list"] if v["name"] == "state"]
    offered = {o["value"] for o in variable["options"]}
    expected = {"Done": {"done"}, "Running": {"progressing", "stalled", "locked"},
                "Stalled or locked": {"stalled", "locked"}, "Failed": {"failed"}}
    for title, states in expected.items():
        (link,) = by_title[title]["fieldConfig"]["defaults"]["links"]
        pattern = selected(link["url"])
        assert pattern in offered
        assert {n for n, *_ in design.STATES if re.fullmatch(pattern, n)} == states
    every = next(o["value"] for o in variable["options"] if o["text"] == "All")
    assert {n for n, *_ in design.STATES if re.fullmatch(every, n)} == {n for n, *_ in design.STATES}
    assert variable["current"]["value"] == every



def run_in_prometheus(monkeypatch, tmp_path):
    """`compose exec ... prometheus <command>` run here, the target file being a file under tmp_path."""
    import subprocess
    from tests.support.patching import checked
    monkeypatch.setattr(monitoring, "TARGETS", str(tmp_path / "load.json"))

    def compose(*args, check=True):
        command = list(args[args.index("prometheus") + 1:])
        return subprocess.run(command, capture_output=True, text=True, check=check).stdout
    checked(monkeypatch, monitoring, "compose", compose)
    return tmp_path / "load.json"


def test_prometheus_reads_the_one_exporter_named_in_its_target_file(monkeypatch, tmp_path):
    import json
    targets = run_in_prometheus(monkeypatch, tmp_path)
    assert monitoring.current_target() == ""
    monitoring.set_target("192.0.2.10:9108")
    assert json.loads(targets.read_text()) == [{"targets": ["192.0.2.10:9108"], "labels": {"where": "aws"}}]
    assert monitoring.current_target() == "192.0.2.10:9108"
    monitoring.set_target(monitoring.LOCAL_TARGET)
    assert json.loads(targets.read_text()) == [{"targets": ["host.docker.internal:9108"], "labels": {"where": "local"}}]


def test_status_reads_an_aws_target_without_asking_for_the_macs_exporter(monkeypatch, tmp_path, capsys):
    from tests.support.patching import checked
    run_in_prometheus(monkeypatch, tmp_path)
    monitoring.set_target("192.0.2.10:9108")
    checked(monkeypatch, monitoring, "services", lambda: [{"Service": "prometheus", "State": "running", "Health": "healthy"}])
    checked(monkeypatch, monitoring, "exporter_answer", lambda: pytest.fail("the Mac's exporter was asked"))
    checked(monkeypatch, monitoring, "scrape_health", lambda: "up")
    checked(monkeypatch, monitoring, "api", lambda method, path, body=None: (200, {}))
    assert monitoring.status() == 0
    assert "a load task's on AWS: 192.0.2.10:9108" in capsys.readouterr().out


def test_a_step_whose_processes_run_elsewhere_publishes_no_cpu_or_memory_rather_than_a_zero():
    row = {**SNAPSHOT["running"][0], "cpu": None, "memory_mb": None}
    text = exporter.render({**SNAPSHOT, "running": [row]})
    assert "load_step_attempt{" in text
    assert "load_step_cpu_percent" not in text and "load_step_memory_mb" not in text
