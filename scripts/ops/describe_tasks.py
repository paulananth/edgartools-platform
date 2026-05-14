"""Print task metadata as TSV: task_id TAB def TAB elapsed TAB cmd."""
import json
import sys
from datetime import datetime, timezone

data = json.load(sys.stdin)
for t in data.get("tasks", []):
    tid     = t["taskArn"].split("/")[-1]
    td      = t.get("taskDefinitionArn", "").split("/")[-1]
    cmd     = " ".join((t.get("overrides", {}).get("containerOverrides") or [{}])[0].get("command", []))[:60]
    started = t.get("startedAt", "")
    elapsed = ""
    if started:
        dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
        elapsed = str(int((datetime.now(timezone.utc) - dt).total_seconds() / 60)) + "m"
    print(f"{tid}\t{td}\t{elapsed}\t{cmd}")
