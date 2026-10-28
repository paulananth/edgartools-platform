# Remaining test review and retirement

PR #1197 merged the first 127 redundant executions. Its original report is
historical evidence. This follow-up starts from `5f264261c` and removes 63 more
cases after reconciling the unfinished draft with subsequent main changes.
Two reviewed activation duplicates remain while another runtime changes that
file. The operator's ruling remains: retire only proven redundancy.

## Collection

The earlier full source review covered 4,292 Python case IDs. Reconciliation
adds 48 explicitly reviewed IDs and checks 16 changed existing Python bodies
and eight added Rust tests. All 4,198 current baseline IDs have a review
decision, with none missing; all 238 Rust test declarations are retained.
These are source-review counts, not claims that each case ran locally.

| Collection | Before | After | Removed |
|---|---:|---:|---:|
| Default | 4,170 | 4,107 | 63 |
| PostgreSQL | 4,182 | 4,119 | 63 |
| MySQL | 4,188 | 4,125 | 63 |
| SQL Server | 4,106 | 4,057 | 49 |
| Unique IDs across these collections | 4,198 | 4,135 | 63 |

All eight collections completed without errors. There are no added cases,
new skips, deselection rules, packed assertions or CI changes. Existing loops
and fixture vectors remain unchanged. Collection counts measure maintenance
surface; runtime improvement has not been measured. SQL Server's existing
refusal and storage checks remain; full workflow support is still deferred.

The two retirement PRs remove 190 default-collected cases in total, 4.46% of
the original 4,262-case denominator. This is a historical removal count, not
the current count difference: other merged changes added and renamed tests.
The original 75% target does not justify losing distinct behavior.

## Five-whys outcomes

Each removed ID, its retained proof and its equivalence rationale is recorded
in [completion-retirement.json](completion-retirement.json).

| Area | Removed | Obligation and retained proof |
|---|---:|---|
| Architecture | 11 | Exact manifest contents, resolver invocation, skeleton status, slug rules and complete installation order imply the weaker checks. Four shell syntax checks duplicate the mandatory CI syntax step over the same files. |
| Unit | 3 | Per-table SQL assertions imply the global checks; an empty not-built exception set made one rules check vacuous. Actual command and flag checks remain. |
| Source engine | 14 | Three publication-count refusals have identical retained shipped-contract setups. Eleven exact malformed JSON frames already execute in the retained finite-frame test; the unique alternative-key case remains. |
| MDM | 9 | Seven uppercase place-code answers remain in a fixed expected-map digest; lowercase normalization remains separate. Registry closure and the existing old-shape field-selection case imply the other two checks. |
| Obsolete implementation checks | 4 | The retired business routines and former closure SQL no longer exist. Their text-scanning plan-cache checks no longer police active behavior. Active indexed-read, migration, grants and retired-call guards remain. This is retirement of an obsolete obligation, not an equivalent behavior test. |
| Storage and installed callers | 22 | Fourteen read labels invoke the same current scenarios in the installed matrix. Waiting includes both lookup assertions. Installed producer includes current/history assertions for the same configuration and kinds. Separate-worker recovery retains its entire helper body, called by the installed matrix instead of also being collected directly. |

The installed matrix retains 160 cases per engine, two configured kinds and
all 18 qualification families. Final CI must prove those installed cases and
their cleanup on PostgreSQL and MySQL. Local collection alone does not qualify
the installed matrix. Four older replacement links now point directly to the
retained producer case, avoiding references to retired intermediate tests.

## Local evidence

- Architecture/unit cohort: 142 passed, 39.96 seconds.
- Engine/MDM cohort: 235 passed, 5.40 seconds, using the native extension built
  from this branch. These ran before the two overlapping activation deletions
  were restored; the restored file was checked separately below.
- Restored activation, generic skill lint and retired-call guard: 179 passed,
  18.09 seconds.
- Retained assertions rejected all 23 injected faults. Two faults exercise
  the activation replacements whose removals are deferred.
- Affected retained storage cases: 11 PostgreSQL passed, 204.31 seconds;
  11 MySQL passed, 219.60 seconds. Private logs and caches are separate for
  each engine; existing test servers were retained.
- The retained populated owner-retirement case passed on PostgreSQL in
  5.96 seconds. It asserts the final routine set is exactly the two storage
  guards, preserving rows, constraints, restricted grants and duplicate replay.
  The earlier snapshot routine is dropped by migration 020; normal owner
  installation calls `prepared_registry.initialize` and retirement 028 for
  the remaining business routines. Historical declarations do not describe
  the final installed schema.
- Shared worker helper body remains AST-identical; its sibling scenario
  resolution is unchanged. No production code or historical migration changes.

Final CI is recorded in the ticket when complete.
Logs, source-level review ledgers and diagnostics remain private. Source review
is separate from behavioral execution.

## Standards

Fresh Codex branch and worktree from current main. The old draft is preserved
privately with checksums. Luna agents used low reasoning and disjoint edit
areas; root reconciled their decisions. The activation file is excluded after
the overlap guard identified another runtime's work. Local runs use private
testmon caches and bounded timeouts. No acquisition or shared-server lifecycle
changes were made.

## Spec

Every removal has either a complete retained proof or an explicitly obsolete
implementation obligation. Unique refusal, rollback, migration, authorization,
concurrency and recovery coverage remains. A percentage is not a deletion rule.
New main tests are reviewed separately from the earlier full audit.

## GoF

The history shows checkout scenarios followed by an independently installed
matrix reusing those scenarios. Reuse that existing seam and remove duplicate
entry points. The moved worker helper preserves its behavior and has one
installed caller. A new runner abstraction or class hierarchy would add cost
without addressing a demonstrated variation problem. Final CI remains the
load-bearing proof for installed execution.
