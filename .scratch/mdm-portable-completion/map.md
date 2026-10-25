# Complete portable MDM and retire PostgreSQL business logic

Labels: wayfinder:map

## Destination

One configuration-driven normal MDM workflow runs on PostgreSQL and MySQL, with shared Rust/Python computation and database-authoritative storage. Superseded active PostgreSQL business routines and their callers are retired after equivalent behavior is qualified; historical migrations and storage guarantees remain.

## Notes

- **Execution is in scope**, following the operator’s repeated implementation direction and Lavish request to scope the remaining MDM work into tickets. This map decomposes existing authorized work; it does not authorize a new architecture, activation or merge.
- Local Markdown is the shared issue tracker (`docs/agents/issue-tracker.md`). Open child tickets live under `issues/`; their `Blocked by` lines define dependencies. The frontier is the first open, unblocked, unclaimed ticket in number order. Claim before doing its work. Record answers and verification in the ticket, then link its resolution below.
- Consult `mdm-engineering`, `gof-refactor-reviewer` before code, and the three-axis Standards/Spec/GoF review after code. Every ticket has a live Markdown checklist, evidence and actual ET completion stamps; Learning → skill is last.
- Preserve the existing implementation worktree. PR #1148 merged as 4b1bb68f before inventory began. Its native-read/authority checkpoint is qualified foundation, not evidence of complete MySQL support. Each new execution ticket gets a fresh branch from current main and its own worktree; carry required predecessor changes only after ownership and dependency reconciliation.
- The parent portability plan remains [Complete platform database portability before master configuration](../../.planning/workstreams/platform-three-databases/01-migrate.md). The previous broad [MDM completion checklist](../../.planning/workstreams/platform-three-databases/04-mdm-completion.md) retains its historical evidence; this map provides the detailed remaining route without marking that checklist complete.
- Existing rulings remain settled: no entity/source policy in engine code; PostgreSQL and MySQL first; SQL Server last; databases enforce locks, uniqueness, authorization, freshness and atomic effects; generic computation belongs in Rust/Python. No new class hierarchy or parallel merge algorithm is presumed.
- Keep provider access and production unchanged. Use invented fixtures and publish counts/outcomes only. Retain PostgreSQL storage integration tests and existing SQL Server adapter checks. No source activation or named PR merge is authorized by charting.

## Decisions so far

- [Inventory the current caller and preserve unfinished work](issues/01-inventory-current-caller-and-preserve-work.md) — merged WIP retained; all 36 installed functions and remaining caller operations allocated to their replacement tickets; historical SQL and storage enforcement are separately accounted for.
- [Install governed MDM storage on both engines](issues/02-install-governed-portable-store.md) — normal PostgreSQL/MySQL owner installation and retained registry qualification delivered in PR #1152, with skill learning in #1153; both implementation revisions pass all nine checks. Implementation #1152 and skill learning #1153 are merged. Their installed owner/registry evidence does not qualify the complete worker workflow.

- [Connect indexed records to shared matching and scope](issues/03-connect-indexed-record-reads.md) — normal read-only proposal/scope API implemented in PR #1156 with independent installed read smoke on PostgreSQL/MySQL, exact reference/provenance validation and configured native scope indexes. Skill learning is PR #1155. Implementation #1156 and skill learning #1155 are merged. Atomic save is separately qualified in ticket 04.

- [Commit normal merges atomically](issues/04-commit-normal-merge-atomically.md) — implementation #1159 and skill learning #1158 are merged after nine green checks each. Normal assessment/save/replay is qualified on PostgreSQL/MySQL; worker authority and publication recovery remain ticket 06.

- [Connect master reads and operator commands](issues/05-connect-reads-and-operator-commands.md) — active in draft PR #1164. Two configured-kind/source cases per engine pass through the independent five-wheel installation for provenance, revisions/history, aliases/reversal, detail/relationship history, pinned pages, Silver lookup and actual restricted-role Context/inspection CLI. Configured indexed name search and the actual owner rebuild now pass in the independent ca2f6f75 installation for both configured kinds on each engine; local completeness/recovery cases also pass. Forced publication explicitly refuses pending ticket 06. Final CI remains open. Separate reader skill learning is draft PR #1165, tracked in [ticket 12](https://github.com/paulananth/edgartools-platform/blob/codex/mdm-reader-storage-learning-20261024/.scratch/mdm-portable-completion/issues/12-reader-storage-skill-learning.md) on its own branch.

## Not yet specified

- Exact replacement implementation details and final DROP signatures/dependency order must be pinned by the replacement and retirement tickets. The source/catalog baseline and responsibility assignments now live in the resolved inventory ticket.
- Any further capability gap demonstrated by the normal caller may yield a bounded new child ticket. Broad Rules or Bookkeeping conversion stays outside this destination.

## Out of scope

- Full SQL Server workflow qualification; it follows the PostgreSQL/MySQL gate in the parent program.
- RDM completion already landed; Silver’s remaining type/link qualification has its own parent-plan scope. This map includes only the real MDM lookup interface Silver needs.
- Company, Person, Security and relationship onboarding; configuration freeze and captured-input proving occur after portability.
- Hosted migration, cutover, source activation, external acquisition, and AWS Postgres.
