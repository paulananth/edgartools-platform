"""The load monitor dashboard, built from the design tokens: every colour and threshold comes from `design`, every panel
says in its description which interaction it carries and what a reading means. Pushed by `monitoring.py`; never edited by hand."""
import design

UID = "load-monitor"
SOURCE = {"type": "prometheus", "uid": "prometheus"}


def steps(*limits_colours) -> dict:
    return {"mode": "absolute", "steps": [{"color": colour, "value": value} for value, colour in limits_colours]}


def target(expr: str, ref: str = "A", legend: str = "", fmt: str = "time_series", instant: bool = False) -> dict:
    return {"datasource": SOURCE, "expr": expr, "refId": ref, "legendFormat": legend, "format": fmt, "instant": instant,
            "range": not instant}


def stat(title: str, description: str, expr: str, x: int, thresholds: dict, unit: str = "none", decimals: int = 0,
         graph: str = "area") -> dict:
    return {"type": "stat", "title": title, "description": description, "datasource": SOURCE,
            "gridPos": {"h": 4, "w": 4, "x": x, "y": 0}, "targets": [target(expr)],
            "fieldConfig": {"defaults": {"thresholds": thresholds, "color": {"mode": "thresholds"}, "unit": unit,
                                         "decimals": decimals, "mappings": []}, "overrides": []},
            "options": {"colorMode": "background", "graphMode": graph, "textMode": "value", "justifyMode": "center",
                        "reduceOptions": {"calcs": ["lastNotNull"], "values": False}}}


def header() -> list[dict]:
    d = design
    zero_green = lambda colour: steps((None, d.GREEN), (1, colour))
    return [
        stat("Done", "Steps finished. The number ticks up when a step's block turns blue on the lanes below.",
             'load_steps{state="done"}', 0, steps((None, d.NEUTRAL), (1, d.BLUE))),
        stat("Running", "Steps with a process now: progressing, stalled or locked.",
             'sum(load_steps{state=~"progressing|stalled|locked"})', 4, steps((None, d.NEUTRAL), (1, d.GREEN))),
        stat("Failed", "Steps the scheduler gave up on. Any is red: a retry cannot change a repeated failure.",
             'load_steps{state="failed"}', 8, zero_green(d.RED), graph="none"),
        stat("Stalled or locked", "Running steps with no sign of work, or waiting on database locks. Orange from one.",
             'sum(load_steps{state=~"stalled|locked"})', 12, zero_green(d.ORANGE), graph="none"),
        stat("Lock waiters", "Sessions waiting on database locks: one is normal (amber), three is the scheduler's limit (red).",
             "load_lock_waiters", 16, steps((None, d.GREEN), (d.LOCK_WAITERS[0], d.AMBER), (d.LOCK_WAITERS[1], d.RED)), graph="none"),
        stat("Memory free", "Share of memory free. Short under a quarter (orange), pressed under a tenth (red): the controller holds lanes back.",
             "load_machine_memory_free_ratio", 20,
             steps((None, d.RED), (d.MEMORY_FREE[0], d.ORANGE), (d.MEMORY_FREE[1], d.GREEN)), unit="percentunit"),
    ]


def lanes() -> dict:
    mappings = {str(code): {"text": name, "color": colour, "index": code} for name, code, colour, _ in design.STATES}
    return {"type": "state-timeline", "title": "Lanes", "datasource": SOURCE,
            "description": "One row a step, grouped by lane. A step is grey while it waits, green while it works, "
                           "orange or red when it is stalled or locked, blue when done and dark red "
                           "when it failed. A change of colour is the event; hover a bar for the step and its state. "
                           + " ".join(f"{name}: {meaning}." for name, _, _, meaning in design.STATES),
            "gridPos": {"h": 16, "w": 24, "x": 0, "y": 4},
            "targets": [target("load_step_state", legend="{{lane}} · {{step}}")],
            "fieldConfig": {"defaults": {"mappings": [{"type": "value", "options": mappings}], "color": {"mode": "fixed"},
                                         "custom": {"fillOpacity": 85, "lineWidth": 0}}, "overrides": []},
            "options": {"mergeValues": True, "showValue": "never", "alignValue": "center", "rowHeight": 0.85,
                        "legend": {"showLegend": False}, "tooltip": {"mode": "single", "sort": "none"}}}


def table(title: str, description: str, targets: list[dict], rename: dict, y: int, x: int, w: int, overrides=(),
          merge: bool = True) -> dict:
    """A table of instant readings: the scrape's own labels and the time are hidden, the rest renamed for the operator."""
    hidden = {"Time": True, "__name__": True, "state": True, "instance": True, "job": True, "Value": not merge}
    steps_ = ([{"id": "merge", "options": {}}] if merge else []) + [
        {"id": "organize", "options": {"excludeByName": hidden, "renameByName": rename}}]
    return {"type": "table", "title": title, "description": description, "datasource": SOURCE,
            "gridPos": {"h": 10, "w": w, "x": x, "y": y}, "targets": targets, "transformations": steps_,
            "fieldConfig": {"defaults": {"custom": {"cellOptions": {"type": "auto"}}}, "overrides": list(overrides)},
            "options": {"showHeader": True, "cellHeight": "sm"}}


def colored(field: str, thresholds: dict, unit: str = "none") -> dict:
    return {"matcher": {"id": "byName", "options": field},
            "properties": [{"id": "thresholds", "value": thresholds}, {"id": "unit", "value": unit},
                           {"id": "custom.cellOptions", "value": {"type": "color-background"}}]}


def running_table() -> dict:
    d = design
    exprs = [("load_step_attempt", "Attempt"), ("load_step_workers", "Workers"), ("load_step_elapsed_minutes", "Elapsed min"),
             ("load_step_bound_minutes", "Bound min"), ("load_step_log_age_minutes", "Log age min"),
             ("load_step_cpu_percent", "CPU %"), ("load_step_memory_mb", "Memory MB"), ("load_step_rows_per_minute", "Rows/min"),
             ("load_step_cause", "Why")]
    targets = [target(e, chr(65 + i), fmt="table", instant=True) for i, (e, _) in enumerate(exprs)]
    rename = {f"Value #{chr(65 + i)}": name for i, (_, name) in enumerate(exprs)}
    rename.update({"lane": "Lane", "step": "Step"})
    return table("Running now", "Each running step. Attempt 2 or more means a restart. Log age turns amber at ten minutes and "
                 "red at twenty: the first sign of a stall. A step with no CPU, no session of its own working and a silent log is stalled. Why is the last of the step's five whys.",
                 targets, rename, 20, 0, 14,
                 [colored("Log age min", steps((None, d.GREEN), (d.LOG_AGE_MINUTES[0], d.AMBER), (d.LOG_AGE_MINUTES[1], d.RED))),
                  colored("Attempt", steps((None, d.GREEN), (2, d.AMBER)))])


def waiting_table() -> dict:
    return table("Waiting for", "Each step that has not started and the step it waits for. A step waits only for the source "
                 "whose golden records its own records join; an empty cell means it waits for a free slot.",
                 [target('load_step_info{state="waiting"}', fmt="table", instant=True)],
                 {"lane": "Lane", "step": "Step", "waits_for": "Waits for"}, 20, 14, 10, merge=False)


def whys_table() -> dict:
    """The five whys of every running step that is not progressing: what it shows, why, and what that waits on, down to the cause."""
    panel = table("Why a step is not working", "The five whys of each running step that is stalled or locked, each read from the step's own "
                  "sessions, CPU and log: the symptom, its database sessions, its latest statement, what it waits on, and the cause. A "
                  "line that says not measured names what would measure it. Empty while every running step works.",
                  [target("load_step_why", fmt="table", instant=True)],
                  {"lane": "Lane", "step": "Step", "number": "Why #", "why": "Because"}, 30, 0, 24, merge=False)
    panel["gridPos"]["h"] = 9
    panel["transformations"].append({"id": "sortBy", "options": {"sort": [{"field": "Step"}, {"field": "Why #"}]}})
    return panel


def rate() -> dict:
    return {"type": "timeseries", "title": "Rows written a minute", "datasource": SOURCE,
            "description": "Rows written to each store a minute, counted when a transaction commits. A flat line while steps "
                           "run is the stall to look for; the colour of a step's block says which.",
            "gridPos": {"h": 8, "w": 24, "x": 0, "y": 39}, "targets": [target("load_store_rows_per_minute", legend="{{store}}")],
            "fieldConfig": {"defaults": {"custom": {"fillOpacity": 20, "lineWidth": 2, "spanNulls": True}, "unit": "none"}, "overrides": []},
            "options": {"legend": {"displayMode": "list", "placement": "bottom"}, "tooltip": {"mode": "multi"}}}


def annotations() -> list[dict]:
    def note(name: str, colour: str, expr: str, title: str) -> dict:
        return {"datasource": SOURCE, "enable": True, "name": name, "iconColor": colour, "expr": expr, "step": "30s",
                "titleFormat": title, "textFormat": "{{step}} (lane {{lane}})"}
    return [note("Restarts", design.AMBER, "changes(load_step_attempt[1m]) > 0", "Attempt restarted"),
            note("Failures", design.RED, f"(changes(load_step_state[1m]) > 0) and (load_step_state == {design.CODE['failed']})", "Step failed")]


def build() -> dict:
    return {"uid": UID, "title": "Load monitor", "tags": ["load", "monitoring"], "timezone": "America/New_York",
            "refresh": "10s", "time": {"from": "now-6h", "to": "now"}, "schemaVersion": 39, "editable": False,
            "graphTooltip": 1, "annotations": {"list": annotations()},
            "panels": [*header(), lanes(), running_table(), waiting_table(), whys_table(), rate()],
            "description": "Is the load healthy, and why is a step not running? Colour carries the answer: read the lanes, "
                           "then the stat strip. Built from skills/load-monitoring."}
