# Five whys: retire repeated execution, keep distinct proof

This is the initial pass merged in PR #1197. The subsequent full source review
and current-main reconciliation are tracked in [COMPLETION.md](COMPLETION.md)
and [COMPLETION-EVIDENCE.md](COMPLETION-EVIDENCE.md).

Baseline `0a1470c1a`: **4,262 collected Python cases**. The original 75% request
would require removing 3,197 cases. After the first evidence pass, the operator
selected **“Retire only proven redundancy”**. This bounded change removes
**127 cases (2.98%)**, leaving **4,135**. It does not claim a 75% reduction or
that every remaining test is irreducible.

Collection uses the same committed test tree, `--collect-only`, importlib mode
(to distinguish two existing `test_installed.py` modules), and the missing local
profiling dependency supplied transiently. There are no collection errors. This
counts Python node IDs once, before the CI database matrix multiplies them.
Rust tests, runtime settings, CI gates, skip markers and production code are
unchanged. Collection counts do not establish a runtime speedup.

## Five whys for each retired family

| Family / cases removed | 1. Why did it exist? | 2. Why does that matter? | 3. Why is the path current? | 4. Why was a second test needed? | 5. Why retire this execution? |
| --- | --- | --- | --- | --- | --- |
| Merge / 58 | Run 29 save scenarios for two configured kinds. | Wrong binding, stale work or failed atomicity corrupts mastering. | The normal configured Merge Stage remains active on both engines. | It was needed before the complete installed matrix existed. | The installed matrix runs the **same `record_read_scenarios` code**, same case/kind, restricted database roles and real engines, and additionally verifies package revisions/import paths. Scope and rollback cases absent from that matrix remain in the checkout suite. |
| Master reads / 38 | Exercise 19 current/history/context cases for both kinds. | Readers must retain history, provenance, published time and alias meaning. | Consumer and Context callers remain active. | Checkout invocation supplied the first normal-caller proof. | Each removed case/kind runs the same `master_read_scenarios` code in the installed matrix. Unknown identifiers, forced-publication refusal and missing-search configuration are not equivalent cases and remain. |
| Silver identifiers / 6 | Exercise Unicode, chunking and actual Silver lookup for both kinds. | Wrong master lookup corrupts Silver identity references. | Silver still uses this interface. | These normal checkout cases preceded independent installed qualification. | The installed matrix runs the same `master_id_scenarios` code; its Silver case still creates the separate destination. Lookup, waiting, merge and concurrency cases remain in the checkout suite. |
| Search / 8 | Exercise words, changed content, query plans and rebuild for both kinds. | Search must be complete, indexed and recoverable. | Configured name search remains current. | Initially only the checkout wrapper ran these scenarios. | The installed matrix invokes the same `master_search_scenarios` code. Ranking, legacy-gap refusal, concurrency, configuration, maintenance and paging are distinct cases and remain. |
| Workers/publication / 16 | Exercise all eight worker/publication cases for two kinds. | Authority, frozen mappings, Journal delivery and recovery must survive. | These worker paths remain current. | The wrapper provided a real-role proof before the installed matrix. | All eight cases and both kinds run the same `worker_publication_scenarios` code in the installed jobs. Remove the now-unused wrapper module; keep every scenario assertion, separate-process proof and cleanup check. |
| Classification / 1 | Verify an operating-company verdict wins for a person-shaped record. | Rule order determines the selected kind. | The configured classifier remains current. | Two differently named tests contain the identical body and same fixture. | `test_an_earlier_step_wins_over_a_later_one` keeps the exact assertion. AST equality verified; an injected wrong verdict makes that retained test fail. |

The installed matrix still executes **164 cases on PostgreSQL and 164 on
MySQL**. Each of the 126 removed checkout scenarios maps to a retained
installed case/kind in [retirement.json](retirement.json). No missing
replacement is accepted. Shared scenario files, installed assertions and CI
configuration are byte-for-byte unchanged. Existing SQL Server adapter
checks and the normal-workflow refusal remain; full SQL Server qualification
is still deferred.

## Families retained during this pass

These are reasons to retain distinct obligations, not a claim that every case
in these families has been individually proved minimal.

- **Storage adapters:** a successful save does not prove forbidden writes,
  stale fences, transaction rollback, migration recovery or concurrent writers.
  Keep those real-engine checks.
- **Installed workflow:** checkout execution cannot catch an omitted wheel
  asset, wrong revision or runtime imported from the checkout. Keep the complete
  installed matrix and before/after import checks.
- **Source engine and captured-source contracts:** generic reader coverage does
  not prove every configured source's fields, dates, ordinals, scope or retained
  raw data. Keep the per-source cases and Rust acceptance tests.
- **MDM calculation/configuration:** happy-path mastering does not establish
  every rejection, identity ordering, field winner, relationship interval,
  precision boundary or approval pin. Keep distinct expected answers.
- **RDM/Silver:** MDM qualification does not prove their own approval/history,
  exact types, append/upsert/snapshot, registration, transport or indexes.
- **Bookkeeping/Journal:** a successful worker is not proof of lease fencing,
  missing acknowledgement recovery, publication integrity or dependency
  corruption refusal.
- **AWS/deployment/security:** runtime mastering does not exercise account
  checks, secrets redaction, deployment ordering, access boundaries or required
  image assets.
- **Profiling/unit contracts:** database lifecycle tests do not prove mixed
  input shapes, lossless numbers, provider-independent configuration or
  credential redaction.

## Review

### Standards

Fresh Codex worktree and branch; existing worktrees untouched. The prospective
guard found no overlap for eight candidate paths, and the actual guard found
none for the edited paths. Per-session private logs/testmon caches, bounded
local runs and transient local dependency supply. No provider request or shared
server lifecycle change. Exact retired IDs and their retained proof are public;
source values and diagnostics remain private.

### Spec

The operator revised the percentage target to proven redundancy. Every removed
case has a named current replacement. No parameter loops are hidden inside a
single test to change the denominator; no skip/deselection is added; no unique
case or production behavior is removed. Future reductions need the same
case-level proof.

### GoF

History `4fb26ae4` → `b2558899` → `6744302a` shows normal checkout wrappers
followed by a complete independently installed matrix using the same scenario
modules. Reuse that existing runner and delete duplicate entry points. No new
runner abstraction or test class hierarchy is justified. The retained installed
jobs are load-bearing: their unchanged aggregate CI gate must pass before merge.

## Learning → skill

None. The existing mdm-engineering “Choose the cheapest proof” and independent
installed qualification rules already apply. No missing shared skill procedure
was demonstrated.

## Bounded local verification

- Affected classification and CI-contract cohort: **49 passed**, 3.13 seconds.
- Retained normal merge/read/ID/search cases: **30 PostgreSQL passed**, 123.96 seconds; **30 MySQL passed**, 176.27 seconds.
- Retired-to-retained manifest: **127 mapped**, zero missing replacement cases.
- Classification fault: retained assertion rejects an injected wrong verdict.
- Collection: **4,262 → 4,135**, both error-free; no cases added or hidden.
- Full final-head CI and installed matrix remain the PR merge gate.
