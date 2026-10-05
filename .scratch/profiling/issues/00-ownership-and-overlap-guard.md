# 00 Ownership and overlap guard

Type: task. Phase: A. Blocked by: —. Map: [map](../map.md). Plan: [plan](../plan.md).

## Checklist

- [x] Add the path-ownership section to AGENTS.md and CLAUDE.md. Verified by diff; 2026-10-04 20:37 ET
- [x] Write scripts/dev/overlap_guard.sh. 2026-10-04 20:37 ET
- [x] Guard passes on this branch and stops a test edit to a file in an open Codex PR. Verified: exit 0 clean; exit 1 naming PR #822 and its worktree for skills/data-platform/COMBINING.md; 2026-10-04 20:37 ET
- [x] Write the map and one ticket per build row. Verified every map link resolves; 2026-10-04 20:37 ET
- [x] Operator approves the ownership section. Operator: "merge 823"; 2026-10-04 20:41 ET
- [x] PR, CI green, merge on the operator's word. PR #823, all 6 checks passed, squash-merged as 259f954c; 2026-10-04 20:41 ET
