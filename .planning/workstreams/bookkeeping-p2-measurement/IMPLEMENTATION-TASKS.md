# Bookkeeping measurement implementation tasks

Status: proposed, awaiting operator approval. No implementation has started.

Aggregated from the latest CEO/DX/engineering JSONL run for this exact branch,
filtered to the current last-five-commit window and exact-deduplicated by
(component, sorted files, title). Rebase mappings retain original review commits.
Five tasks survived. Priority sort is not execution order.

**Execute sequentially: C1 → C2 → D1 → E5 → E6**, with tests alongside each task.
Use a fresh Codex branch/worktree after plan approval; recheck live ownership first.
Touch only the four new code/test paths below. Existing shared helpers/production
modules/test files/skills remain unchanged. Raw model artifacts stay outside Git.

## Tasks

- [ ] **C2 (P1, human: 4h / coding agent: 1h) — evidence contract** — Separate fixture state timing diagnostics and eligibility
  - Surfaced by: ceo-review — CEO six independent findings
  - Files: scripts/benchmarks/benchmark_bookkeeping_control.py, tests/unit/test_bookkeeping_control_benchmark.py
  - Verify: U06/U07/U09/U10/U11, P11/P12/P14; safe schema, fresh state and truthful nullable counters.

- [ ] **C1 (P1, human: 4h / coding agent: 1h) — lifecycle** — Bound and identify every owned local resource
  - Surfaced by: ceo-review — CEO lifecycle/cleanup gap
  - Files: scripts/benchmarks/bookkeeping_benchmark_support.py, tests/unit/test_bookkeeping_control_benchmark.py, tests/integration/test_bookkeeping_control_cost_postgres.py
  - Verify: U04/U05/U08/U12, P01/P02/P13/P15; exact owned cleanup and foreign sentinel.

- [ ] **E6 (P1, human: 1 day / coding agent: 2h) — proof** — Prove roles CLI routing metric preservation privacy deadlines and owned cleanup
  - Surfaced by: eng-review — Engineering full path diagram: 27 required unimplemented proof groups
  - Files: tests/unit/test_bookkeeping_control_benchmark.py, tests/integration/test_bookkeeping_control_cost_postgres.py
  - Verify: All 27 proof groups, successful warm default smoke within budget, Standards/Spec/GoF review and required CI.

- [ ] **D1 (P1, human: 3h / coding agent: 45min) — CLI/docs** — Implement import-light help exact flags safe outcomes and copy-paste guidance
  - Surfaced by: devex-review — DX passes 1-6: first-use prerequisites, flags, safe errors and report semantics
  - Files: scripts/benchmarks/benchmark_bookkeeping_control.py, tests/unit/test_bookkeeping_control_benchmark.py, tests/integration/test_bookkeeping_control_cost_postgres.py
  - Verify: U01/U02/U03, P10; import-light help, offline warm command, exact flags/output/errors and CLI JSON semantics.

- [ ] **E5 (P2, human: 1 day / coding agent: 2h) — protocol measurement** — Implement frozen synthetic cases receipt closure fresh state and truthful metrics
  - Surfaced by: eng-review — Engineering E1/E3/E4: actual input-linked dependencies and precise metric coverage
  - Files: scripts/benchmarks/benchmark_bookkeeping_control.py, tests/integration/test_bookkeeping_control_cost_postgres.py
  - Verify: P04–P09/P11/P12; every catalog family, correct receipt closure, J-fixed backlog and clean cloned state.

- [ ] **Learning → skill** — name a demonstrated correction, or none, with verification and an actual ET completion stamp.

## Scope and completion rules

Keep a live Markdown checklist in the implementation ticket. Add new parts when
findings surface, never delete deferred work, and timestamp only verified completions.
A successful warm smoke is required; an honest timeout is failure-handling proof only.
No performance/complexity threshold, runtime optimization, limit change, provider call,
source qualification, hosted deployment, root README edit or comparator is authorized
by these tasks. Merging requires full green CI and explicit named operator approval.

Provisional total: 3–4 human days / 7–10 active coding-agent hours plus proof/CI elapsed.
Per-task estimates overlap some verification; they are planning estimates, not a
delivery guarantee. Local test batches remain under five minutes; exact assertions
and commands are in [TEST-PLAN.md](TEST-PLAN.md). Case contract: [CASE-MATRIX.md](CASE-MATRIX.md).
