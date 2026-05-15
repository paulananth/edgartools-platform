"""Parse Step Functions execution history JSON from stdin and print stage results + failed task IDs."""
import json
import sys


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        print("  (no history)")
        return

    events = data.get("events", [])
    status_map: dict = {}
    task_ids: list = []

    for e in events:
        s = (e.get("stateEnteredEventDetails") or {}).get("name", "")
        x = (e.get("stateExitedEventDetails")  or {}).get("name", "")
        if s:
            status_map[s] = "▶"
        if x:
            status_map[x] = "✓"

        fd = e.get("taskFailedEventDetails") or {}
        cause = fd.get("cause", "")
        if cause:
            try:
                c = json.loads(cause)
                tid = c.get("TaskArn", "").split("/")[-1]
                if tid:
                    task_ids.append(tid)
                for cont in c.get("Containers", []):
                    ec = cont.get("ExitCode", "?")
                    reason = (cont.get("Reason") or "")[:40]
                    for st in list(status_map):
                        if status_map[st] == "▶":
                            status_map[st] = f"✗ exit={ec} {reason}"
            except Exception:
                pass

    # Exec-level / map-level failures
    for e in events:
        for key in ("executionFailedEventDetails", "mapRunFailedEventDetails"):
            ef = e.get(key) or {}
            if ef.get("error"):
                print(f"  Error: {ef['error']}  {ef.get('cause','')[:100]}")
                break

    print()
    print("  Stage results:")
    for stage, result in status_map.items():
        print(f"    {result}  {stage}")

    print()
    print("  Failed task IDs (most recent first):")
    for t in reversed(task_ids[-3:]):
        print(f"    {t}")

    # Print the most recent task ID on its own line for shell capture
    if task_ids:
        print(f"\nLATEST_TASK_ID={task_ids[-1]}")


if __name__ == "__main__":
    main()
