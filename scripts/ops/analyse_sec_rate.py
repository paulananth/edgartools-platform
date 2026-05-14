"""Analyse SEC request rates from a CloudWatch log event page (aws logs get-log-events JSON)."""
import json
import sys
from collections import defaultdict


def main():
    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
    except Exception:
        print("  (no logs)")
        return

    msgs = []
    for e in data.get("events", []):
        try:
            d = json.loads(e["message"])
            d["_ts"] = e["timestamp"] / 1000
            msgs.append(d)
        except Exception:
            pass

    sec_msgs = [m for m in msgs if m.get("event", "").startswith("sec_pull")]
    if not sec_msgs:
        print("  (no SEC pull events yet)")
        return

    first = min(m["_ts"] for m in sec_msgs)
    last  = max(m["_ts"] for m in sec_msgs)
    span_min = max((last - first) / 60, 1 / 60)

    by_host: dict = defaultdict(lambda: defaultdict(int))
    for m in sec_msgs:
        host = m.get("host", "unknown")
        evt  = m.get("event", "")
        by_host[host][evt] += 1

    total_started = sum(v.get("sec_pull_started", 0) for v in by_host.values())
    total_failed  = sum(v.get("sec_pull_failed", 0)  for v in by_host.values())
    total_ok      = sum(v.get("sec_pull_completed", 0) for v in by_host.values())
    req_per_min   = total_started / span_min
    req_per_sec   = req_per_min / 60
    fail_pct      = 100 * total_failed / total_started if total_started else 0

    print(f"  Span         : {span_min:.1f} min  ({len(sec_msgs)} events)")
    print(f"  Rate         : {req_per_min:.1f} req/min  =  {req_per_sec:.2f} req/sec")
    print(f"  Outcomes     : {total_ok} ok / {total_failed} failed ({fail_pct:.0f}%)")
    print()
    print("  By host:")
    for host, c in sorted(by_host.items()):
        s   = c.get("sec_pull_started", 0)
        ok  = c.get("sec_pull_completed", 0)
        f   = c.get("sec_pull_failed", 0)
        rpm = s / span_min
        print(f"    {host:<22s}  {s:5d} started  {ok:5d} ok  {f:5d} failed  {rpm:.1f} req/min")

    status_counts: dict = defaultdict(int)
    for m in sec_msgs:
        if m.get("event") == "sec_pull_failed":
            sc = m.get("status_code", m.get("error", "unknown"))
            status_counts[str(sc)] += 1
    if status_counts:
        print()
        print("  Failure breakdown:")
        for sc, n in sorted(status_counts.items(), key=lambda x: -x[1]):
            print(f"    {sc}: {n}")


if __name__ == "__main__":
    main()
