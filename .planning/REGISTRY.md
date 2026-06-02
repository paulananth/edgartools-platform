# Workstream Registry

Agents read this file **before touching any source file**. Update it via:

```bash
scripts/claim-workstream.sh claim <workstream> <runtime> [--phase <phase>] [--plan <plan>] [--blocking <list>]
scripts/claim-workstream.sh release <workstream>
scripts/claim-workstream.sh status
```

Worktree convention: `/Users/aneenaananth/gsd-workspaces/<workstream>/edgartools-platform` on branch `workspace/<workstream>`.

---

## Active Workstreams

### neo4j-pipe

| Field | Value |
|-------|-------|
| **Runtime** | Claude |
| **Status** | active |
| **Branch** | `workspace/neo4j-pipe` |
| **Worktree path** | `/Users/aneenaananth/gsd-workspaces/neo4j-pipe/edgartools-platform` |
| **Claimed at** | 2026-06-01T18:00:00Z |
| **Last session** | 2026-06-01 |
| **Current phase** | Phase 5 — Source To MDM Load Path |
| **Current plan** | TBD (planning next) |
| **Blocking** | Phase 6, Phase 7, Phase 8 |

### mdm-neo4j-dashboard

| Field | Value |
|-------|-------|
| **Runtime** | Claude |
| **Status** | paused |
| **Branch** | `workspace/mdm-neo4j-dashboard` |
| **Worktree path** | `/Users/aneenaananth/gsd-workspaces/mdm-neo4j-dashboard/edgartools-platform` |
| **Claimed at** | 2026-05-24T15:56:29Z |
| **Last session** | 2026-05-24 |
| **Current phase** | Phase 10 — Operator Review Experience |
| **Current plan** | Not started (UI-SPEC approved, execution next) |
| **Blocking** | — |

### neo4j-snowflake

| Field | Value |
|-------|-------|
| **Runtime** | Codex |
| **Status** | active |
| **Branch** | `workspace/neo4j-snowflake` |
| **Worktree path** | `/Users/aneenaananth/gsd-workspaces/neo4j-snowflake/edgartools-platform` |
| **Claimed at** | 2026-05-27T00:24:12Z |
| **Last session** | 2026-05-27 |
| **Current phase** | Phase 3 — Hosted Graph Verification + E2E Cutover |
| **Current plan** | TBD (planning next) |
| **Blocking** | — |

---

## Held Workstreams

### model-builder-contract-gaps

| Field | Value |
|-------|-------|
| **Runtime** | unassigned |
| **Status** | held |
| **Branch** | `workspace/model-builder-contract-gaps` (not yet created) |
| **Worktree path** | `/Users/aneenaananth/gsd-workspaces/model-builder-contract-gaps/edgartools-platform` |
| **Claimed at** | — |
| **Last session** | 2026-05-30 |
| **Current phase** | Phase 1 — Contract Governance (ready to start) |
| **Current plan** | TBD |
| **Blocking** | — |

---

## Released Workstreams

| Workstream | Runtime | Completed | Notes |
|-----------|---------|-----------|-------|
| fix-pipelines | Claude | 2026-05-16 | v1.0 complete, 4 phases |
| fundamentals-stage1parallel | Claude | 2026-05-31 | PRs 1–3 merged to main |
