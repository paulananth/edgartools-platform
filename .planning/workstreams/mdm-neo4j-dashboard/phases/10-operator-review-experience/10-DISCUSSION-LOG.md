# Phase 10: Operator Review Experience - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md; this log preserves the alternatives considered.

**Date:** 2026-05-23T01:07:57Z
**Phase:** 10-operator-review-experience
**Areas discussed:** Review Flow, Filters And Limits, Empty And Error States, Runbook Documentation

---

## Review Flow

### Dashboard Entry

| Option | Description | Selected |
|--------|-------------|----------|
| Triage overview first | Land on a snapshot with attention-needed items, then drill into MDM, Neo4j, and mismatches. | yes |
| Separate review pages first | Keep MDM Overview, Neo4j Overview, and Graph Coverage as distinct primary pages. | |
| Issue-first workflow | Lead with mismatches/pending sync/errors, treating clean counts as secondary context. | |

**User's choice:** Triage overview first.
**Notes:** This matches the operator review goal and preserves detail pages for drill-down.

### Navigation Structure

| Option | Description | Selected |
|--------|-------------|----------|
| Overview, MDM Overview, Neo4j Overview, Mismatch Diagnostics | Rename current sections around the review workflow. | yes |
| Overview, Entities, Relationships, Graph Coverage, Neighborhood | Keep current navigation and polish inside each page. | |
| Overview plus tabs inside one page | Fewer sidebar destinations, with MDM/Neo4j/mismatch tabs in the main view. | |

**User's choice:** Overview, MDM Overview, Neo4j Overview, Mismatch Diagnostics.
**Notes:** Makes mismatch review a first-class operator task.

### Overview Emphasis

| Option | Description | Selected |
|--------|-------------|----------|
| Attention summary first | Blocking errors, warnings, pending sync, missing edges, extra graph data, then high-level counts. | yes |
| Counts first | MDM/Neo4j totals at the top, with warnings beneath. | |
| Readiness checklist first | Config/connectivity/read-only status checklist before metrics. | |

**User's choice:** Attention summary first.
**Notes:** Operators should see what needs action before inspecting details.

### GRAPH-01 Handling

| Option | Description | Selected |
|--------|-------------|----------|
| Include as required fix | Phase 10 must fix entity-domain Neo4j counts by using registry labels, then remove the expected-failure test. | yes |
| Keep separate gap closure | Phase 10 only handles UX polish; GRAPH-01 stays as Phase 9 validation debt. | |
| Mention only in docs | Document the known issue but do not fix it here. | |

**User's choice:** Include as required fix.
**Notes:** The bug affects mismatch review correctness.

---

## Filters And Limits

### Filter Scope

| Option | Description | Selected |
|--------|-------------|----------|
| Per-view filters | Each page owns the filters relevant to its table/view. | |
| Global sidebar filters | One sidebar controls entity type, relationship type, and row limit everywhere. | |
| Hybrid | Global row limit in sidebar, page-specific entity/relationship filters in each view. | yes |

**User's choice:** Hybrid.
**Notes:** Row limit is cross-cutting; entity and relationship filters belong near affected views.

### Default Row Limit

| Option | Description | Selected |
|--------|-------------|----------|
| 50 rows | Enough for useful review while staying bounded. | yes |
| 25 rows | Tighter and faster, but may feel too shallow. | |
| 100 rows | Broader review, but heavier for large stores. | |

**User's choice:** 50 rows.
**Notes:** Keeps diagnostic tables useful without becoming exhaustive exports.

### Row-Limit Choices

| Option | Description | Selected |
|--------|-------------|----------|
| 25 / 50 / 100 / 250 | Simple bounded choices for review. | yes |
| 10 / 25 / 50 | Conservative and fast. | |
| Free numeric input capped at 500 | Flexible, but easier to misuse. | |

**User's choice:** 25 / 50 / 100 / 250.
**Notes:** Allows range while staying explicitly bounded.

### Page-Specific Filters

| Option | Description | Selected |
|--------|-------------|----------|
| Single-select with All default | One entity type or relationship type at a time, defaulting to all. | yes |
| Multi-select with All default | Review several selected types at once. | |
| Searchable text filter | Type-to-filter names in tables. | |

**User's choice:** Single-select with All default.
**Notes:** Easiest to test and keeps large stores bounded.

---

## Empty And Error States

### Missing MDM Configuration

| Option | Description | Selected |
|--------|-------------|----------|
| Blocking error page | Show a clear setup message and stop loading dashboard metrics. | yes |
| Overview warning only | Keep page shell visible but show no data. | |
| Fallback demo state | Show fixture-style placeholder data. | |

**User's choice:** Blocking error page.
**Notes:** MDM is the required source of truth; demo data would be unsafe.

### Neo4j Failure

| Option | Description | Selected |
|--------|-------------|----------|
| Non-blocking warning | MDM pages remain usable; Neo4j and mismatch views show unavailable state. | yes |
| Blocking until fixed | Dashboard stops because graph review is incomplete. | |
| Silent omission | Hide Neo4j data and only show MDM. | |

**User's choice:** Non-blocking warning.
**Notes:** Preserves the Phase 8/9 decision that Neo4j is optional at startup.

### Secret-Safe Error Details

| Option | Description | Selected |
|--------|-------------|----------|
| Env var names and next action only | Show missing variable names and recommended checks, never host/user/password/driver text. | yes |
| Sanitized exception class plus env var names | Include exception type if it helps debugging. | |
| Expandable raw diagnostics | Hidden by default but available for operators. | |

**User's choice:** Env var names and next action only.
**Notes:** Safest for screenshots and shared logs.

### Empty Table Copy

| Option | Description | Selected |
|--------|-------------|----------|
| Neutral empty state | "No rows match the current filters." Use separate warnings for real data gaps. | yes |
| Action prompt | "Try changing filters or row limit." | |
| Success tone | "No issues found." | |

**User's choice:** Neutral empty state.
**Notes:** Empty filtered results are not automatically success or failure.

---

## Runbook Documentation

### Documentation Depth

| Option | Description | Selected |
|--------|-------------|----------|
| Guided review workflow | Launch, required env vars, what to inspect first, how to use filters, common failure states. | yes |
| Launch plus validation only | Commands, env vars, tests. | |
| Troubleshooting matrix first | Error states and fixes before workflow. | |

**User's choice:** Guided review workflow.
**Notes:** Covers the operator path without turning docs into a long troubleshooting manual.

### Operational Commands

| Option | Description | Selected |
|--------|-------------|----------|
| Reference existing commands only | Mention commands like `mdm check-connectivity`, `mdm counts`, `mdm verify-graph`, but no dashboard buttons. | yes |
| No remediation commands | Dashboard docs only describe review. | |
| Detailed runbook commands | Include full command sequences for sync/backfill/repair. | |

**User's choice:** Reference existing commands only.
**Notes:** Helps operators know where to go next while preserving read-only dashboard scope.

### Read-Only Guarantee

| Option | Description | Selected |
|--------|-------------|----------|
| Prominent read-only guarantee section | State no sync, repair, migrate, load, or write actions occur. | yes |
| Brief note in prerequisites | Keep it short. | |
| No, tests cover this | Avoid repeating. | |

**User's choice:** Prominent read-only guarantee section.
**Notes:** Important for operator trust and aligns with architecture guards.

### Validation Instructions

| Option | Description | Selected |
|--------|-------------|----------|
| Focused credential-free test command | The existing dashboard/MDM/graph/architecture test suite. | yes |
| Manual click-through checklist only | Operators verify in browser. | |
| Both automated tests and manual review checklist | Tests plus browser sanity checks. | |

**User's choice:** Focused credential-free test command.
**Notes:** User selected automated validation only instead of the recommended combined automated/manual option.

---

## the agent's Discretion

- Exact Streamlit layout mechanics, component grouping, and README headings.
- Whether the existing `Neighborhood` placeholder is removed or renamed, as long as final navigation matches the locked choices.

## Deferred Ideas

- Manual browser review checklist is not required for Phase 10 documentation.
- Managed AWS-facing deployment remains future work.
- Historical trend views remain future work.
- Drill-through graph visualization remains future work.
