"""Analyse a single batch task's CloudWatch log JSON (from aws logs get-log-events)."""
import json
import sys


def main():
    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
    except Exception:
        print("  (no logs yet)")
        return

    msgs = []
    for e in data.get("events", []):
        try:
            msgs.append(json.loads(e["message"]))
        except Exception:
            pass

    if not msgs:
        print("  (no structured events yet)")
        return

    counts = {}
    for m in msgs:
        k = m.get("event", "")
        counts[k] = counts.get(k, 0) + 1

    STAGES = [
        "silver_database_hydrated",
        "bronze_capture_started",
        "bronze_capture_completed",
        "silver_apply_started",
        "silver_apply_completed",
        "filing_artifact_pipeline_started",
        "filing_artifact_circuit_open",
        "filing_artifact_pipeline_completed",
        "silver_publish_completed",
        "pipeline_failed",
    ]
    stage = next((s for s in reversed(STAGES) if counts.get(s, 0) > 0), "initialising")
    print(f"  Stage        : {stage}")

    bc = next((m for m in msgs if m.get("event") == "bronze_capture_completed"), None)
    sa = next((m for m in reversed(msgs) if m.get("event") == "silver_apply_progress"), None)
    if bc:
        cik_count = bc.get("cik_count", "")
        raw_obj   = bc.get("raw_object_count", "")
        dur       = bc.get("duration_seconds", 0)
        print(f"  Bronze CIKs  : {cik_count}  ({raw_obj} raw objects, {dur:.0f}s)")
    if sa:
        done  = sa.get("ciks_processed", 0)
        total = sa.get("ciks_total", 0)
        print(f"  Silver apply : {done}/{total} CIKs")

    ap  = next((m for m in msgs if m.get("event") == "filing_artifact_pipeline_started"), None)
    apc = next((m for m in reversed(msgs) if m.get("event") == "filing_artifact_pipeline_completed"), None)
    co  = next((m for m in msgs if m.get("event") == "filing_artifact_circuit_open"), None)
    if ap:
        print(f"  Artifact acc : {ap.get('accession_count', '?')} to process")
    if apc:
        print(f"  Artifact done: {apc.get('rows_written', 0)} rows, {apc.get('errors', 0)} errors")
    if co:
        consec = co.get("consecutive_errors", "?")
        print(f"  Circuit open : {consec} consecutive failures triggered breaker")

    started      = counts.get("sec_pull_started", 0)
    retried      = counts.get("sec_pull_retry", 0)
    failed_pulls = counts.get("sec_pull_failed", 0)
    art_failed   = counts.get("filing_artifact_failed", 0)
    if started:
        ok = counts.get("sec_pull_completed", 0)
        fail_pct = 100 * failed_pulls / started if started else 0
        print(f"  SEC pulls    : {ok} ok / {retried} retried / {failed_pulls} failed  ({fail_pct:.0f}% fail rate)")
        if art_failed:
            print(f"  Art failures : {art_failed}  (logged & skipped via per-accession isolation)")

    consec = 0
    max_c  = 0
    for m in msgs:
        if m.get("event") == "filing_artifact_failed":
            consec += 1
            max_c = max(max_c, consec)
        elif m.get("event") == "sec_pull_completed":
            consec = 0
    if max_c:
        pct = 100 * max_c / 20
        bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
        print(f"  Circuit brk  : [{bar}] {max_c}/20 max consecutive")

    events = data.get("events", [])
    if len(events) >= 2:
        span_s = (events[-1]["timestamp"] - events[0]["timestamp"]) / 1000
        span_m = span_s / 60
        print(f"  Log span     : {span_m:.0f} min  ({len(events)} lines)")

    pf = next((m for m in reversed(msgs) if m.get("event") == "pipeline_failed"), None)
    if pf:
        err = pf.get("error_message", "?")[:80]
        print(f"  FAILED       : {err}")


if __name__ == "__main__":
    main()
