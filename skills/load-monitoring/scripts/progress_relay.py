#!/usr/bin/env python3
"""Read meaningful load milestones from Prometheus for an agent conversation."""
from __future__ import annotations

import hashlib
import time
from collections import defaultdict
from urllib.parse import urlencode

PROMETHEUS_QUERY = '{__name__=~"load_.*"}'
GRAFANA_PROMETHEUS_PROXY = "/api/datasources/proxy/uid/prometheus/api/v1/query?"


class RelayUnavailable(Exception):
    """Prometheus or the selected run cannot provide a fresh reading."""


def run_fingerprint(run: str) -> str:
    """Identify the selected run without publishing its label in Prometheus metrics."""
    return hashlib.sha256(run.encode("utf-8")).hexdigest()


def parse_query_response(body: dict) -> dict[str, list[dict]]:
    """Group Prometheus instant-vector samples by metric name."""
    if body.get("status") != "success":
        raise RelayUnavailable("Prometheus query failed")
    result = ((body.get("data") or {}).get("result"))
    if not isinstance(result, list):
        raise RelayUnavailable("Prometheus returned no metric vector")
    metrics: dict[str, list[dict]] = defaultdict(list)
    try:
        for row in result:
            labels = row["metric"]
            name = labels["__name__"]
            value = float(row["value"][1])
            metrics[name].append({"labels": labels, "value": value})
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise RelayUnavailable("Prometheus returned an invalid metric sample") from exc
    return dict(metrics)


def fetch_metrics(api) -> dict[str, list[dict]]:
    """Query the one active exporter through Grafana's existing Prometheus proxy."""
    path = GRAFANA_PROMETHEUS_PROXY + urlencode({"query": PROMETHEUS_QUERY})
    try:
        code, body = api("GET", path)
    except (OSError, ValueError, TypeError) as exc:
        raise RelayUnavailable("Prometheus is unreachable") from exc
    if code != 200 or not isinstance(body, dict):
        raise RelayUnavailable("Prometheus is unreachable")
    return parse_query_response(body)


def _value(metrics: dict[str, list[dict]], name: str, labels: dict[str, str] | None = None) -> float | None:
    for sample in metrics.get(name, []):
        if labels is None or all(sample["labels"].get(key) == value for key, value in labels.items()):
            return sample["value"]
    return None


def _states(metrics: dict[str, list[dict]]) -> dict[tuple[str, str], str]:
    return {(sample["labels"].get("lane", ""), sample["labels"].get("step", "")):
            sample["labels"].get("state", "unknown") for sample in metrics.get("load_step_info", [])}


def _bundles(metrics: dict[str, list[dict]]) -> dict[tuple[str, str], tuple[int, int]]:
    totals: dict[tuple[str, str], int] = {}
    done: dict[tuple[str, str], int] = {}
    for sample in metrics.get("load_step_bundles_total", []):
        labels = sample["labels"]
        totals[(labels.get("lane", ""), labels.get("step", ""))] = int(sample["value"])
    for sample in metrics.get("load_step_bundles_completed", []):
        labels = sample["labels"]
        key = (labels.get("lane", ""), labels.get("step", ""))
        if key in totals:
            done[key] = int(sample["value"])
    return {key: (count, totals[key]) for key, count in done.items()}

def _attempts(metrics: dict[str, list[dict]]) -> dict[tuple[str, str], int]:
    return {(sample["labels"].get("lane", ""), sample["labels"].get("step", "")): int(sample["value"])
            for sample in metrics.get("load_step_attempt", [])}


def _summary(metrics: dict[str, list[dict]]) -> tuple[int, int, int, int, int]:
    total = int(_value(metrics, "load_steps_total") or 0)
    counts = {sample["labels"].get("state", "unknown"): int(sample["value"])
              for sample in metrics.get("load_steps", [])}
    return total, counts.get("done", 0), sum(counts.get(state, 0) for state in ("progressing", "stalled", "locked")), \
        counts.get("waiting", 0), counts.get("failed", 0)


class ProgressRelay:
    """Convert snapshots into one initial update and change-triggered milestones."""

    def __init__(self, run: str, max_snapshot_age: float = 90.0):
        if not run:
            raise ValueError("a load run label is required")
        self.run = run
        self.expected_fingerprint = run_fingerprint(run)
        self.max_snapshot_age = max_snapshot_age
        self.previous: dict | None = None
        self.reported_bundles: dict[tuple[str, str], int] = {}
        self.unavailable = False
        self.complete = False

    def _unavailable(self, reason: str) -> list[str]:
        if self.unavailable:
            return []
        self.unavailable = True
        return [f"LOAD_PROGRESS {self.run}: status unavailable — {reason}."]

    def observe(self, metrics: dict[str, list[dict]]) -> list[str]:
        if _value(metrics, "load_monitor_up") != 1:
            return self._unavailable("the exporter has no healthy reading")
        fingerprints = {sample["labels"].get("run_hash") for sample in metrics.get("load_monitor_run_info", [])}
        if fingerprints != {self.expected_fingerprint}:
            return self._unavailable("Prometheus is not serving this run; refusing mismatched progress")
        age = _value(metrics, "load_monitor_snapshot_age_seconds")
        if age is None or age < 0 or age > self.max_snapshot_age:
            return self._unavailable("the exporter snapshot is stale")

        total, done, active, waiting, failed = _summary(metrics)
        current = {"states": _states(metrics), "attempts": _attempts(metrics), "bundles": _bundles(metrics),
                   "done": done, "total": total, "complete": _value(metrics, "load_complete") == 1}
        summary = f"{done}/{total} steps complete; {active} active, {waiting} waiting, {failed} failed"
        bundle_summary = [f"{'/'.join(part for part in key if part)} bundles {count}/{bundle_total}"
                          for key, (count, bundle_total) in sorted(current["bundles"].items())]
        initial_summary = summary
        if bundle_summary:
            initial_summary += "; " + "; ".join(bundle_summary[:3])
            if len(bundle_summary) > 3:
                initial_summary += f"; {len(bundle_summary) - 3} more active steps"
        recovered = self.unavailable
        self.unavailable = False
        if self.previous is None or recovered:
            self.previous = current
            self.reported_bundles = {key: count for key, (count, _) in current["bundles"].items()}
            if current["complete"]:
                self.complete = True
                return [f"LOAD_PROGRESS {self.run}: COMPLETE — {done}/{total} steps complete."]
            prefix = "monitoring restored; " if recovered else ""
            return [f"LOAD_PROGRESS {self.run}: {prefix}{initial_summary}."]

        changes: list[str] = []
        before_attempts = self.previous["attempts"]
        for key, attempt in current["attempts"].items():
            previous = before_attempts.get(key)
            if previous is not None and attempt > previous:
                label = "/".join(part for part in key if part)
                changes.append(f"{label} restarted (attempt {attempt})")
        before_states = self.previous["states"]
        for key, state in current["states"].items():
            previous = before_states.get(key)
            if state != previous:
                label = "/".join(part for part in key if part)
                if state == "done":
                    changes.append(f"{label} completed")
                elif state == "failed":
                    changes.append(f"{label} failed")
                elif state == "stalled":
                    changes.append(f"{label} stalled")
                elif state == "locked":
                    changes.append(f"{label} blocked on a lock")
                elif state == "progressing":
                    changes.append(f"{label} running")
                elif state == "waiting":
                    changes.append(f"{label} waiting")
                else:
                    changes.append(f"{label} state: {state}")
        for key, (count, bundle_total) in current["bundles"].items():
            previous = self.reported_bundles.get(key, self.previous["bundles"].get(key, (0, bundle_total))[0])
            threshold = max(1, (bundle_total + 19) // 20)
            if count > previous and (count - previous >= threshold or count >= bundle_total):
                label = "/".join(part for part in key if part)
                changes.append(f"{label} bundles {count}/{bundle_total}")
                self.reported_bundles[key] = count
        if current["done"] != self.previous["done"] and not any(word.endswith("completed") for word in changes):
            changes.append(f"{done}/{total} steps complete")
        self.previous = current
        if current["complete"] and not self.complete:
            self.complete = True
            return [f"LOAD_PROGRESS {self.run}: COMPLETE — {done}/{total} steps complete."]
        if changes:
            return [f"LOAD_PROGRESS {self.run}: {'; '.join(changes)}; {summary}."]
        return []


def stream(api, run: str, interval: int = 15, emit=print, sleep=time.sleep) -> int:
    """Poll Prometheus, emitting only verified state changes until this run completes or is interrupted."""
    if interval < 1:
        raise ValueError("poll interval must be at least one second")
    relay = ProgressRelay(run)
    while not relay.complete:
        try:
            events = relay.observe(fetch_metrics(api))
        except RelayUnavailable as exc:
            events = relay._unavailable(str(exc))
        for event in events:
            emit(event)
        if not relay.complete:
            sleep(interval)
    return 0
