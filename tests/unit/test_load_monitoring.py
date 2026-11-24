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


def test_every_state_has_one_code_and_one_colour():
    names, codes, colours = zip(*[(n, c, k) for n, c, k, _ in design.STATES])
    assert len(set(names)) == len(set(codes)) == len(set(colours)) == 6
    # Prometheus keeps the codes it stored: dropping `unclear` leaves code 2 unused, and no other state is renumbered (history would repaint)
    assert sorted(codes) == [0, 1, 3, 4, 5, 6] and "unclear" not in names


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
    log_age = next(o for o in by_title["Running now"]["fieldConfig"]["overrides"] if o["matcher"]["options"] == "Log age min")
    assert [s["value"] for s in log_age["properties"][0]["value"]["steps"]] == [None, *design.LOG_AGE_MINUTES]


def test_the_dashboard_is_code_in_eastern_time_with_restart_and_failure_marks():
    board = dashboard.build()
    assert board["editable"] is False and board["timezone"] == "America/New_York"
    assert {a["name"] for a in board["annotations"]["list"]} == {"Restarts", "Failures"}


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
    monkeypatch.setattr(monitoring.subprocess, "Popen", lambda argv, **k: started.append(argv) or type("P", (), {"pid": 1})())
    monitoring.start_exporter()
    assert len(started) == 1 and started[0][-2:] == [str(monitoring.HERE / "exporter.py"), "serve"][-2:]
