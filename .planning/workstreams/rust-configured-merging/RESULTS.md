# Configured merging and field survivorship

Qualification in progress; no deployment or policy activation.

## Implemented ownership

| Work | Owner and evidence |
|---|---|
| Accepted identity graph replay, default/explicit survivors, merge dependencies, exclusions, bind correction, quarantine and retirement | Rust `crates/source-contract/src/identity.rs`, through the existing Python `replay` API |
| Configured source eligibility, clear authorization, unknown-time eligibility, priority/recency/tie ordering | Rust `crates/source-contract/src/survivorship.rs`, shared by entity and profile fields |
| Policy authority and digests, approved matching, profile qualification, timestamps/age calculation, source-history fold, canonical value comparisons, override interpretation and output materialization | Python `mdm/clean/identity.py` and `survivorship.py`; opaque payload references preserve arbitrary integers, float/bool distinctions and Unicode |
| CLI, integrations, retries, independent verification and database clients | Existing Python worker and MergeStage |
| Indexed retrieval, constraints, atomic commits, shared freshness/fencing, leases, history and recovery | Existing PostgreSQL 16 schema/roles/functions; unchanged in this slice |

The native binding releases the GIL for graph replay and field ranking. Metadata
crosses the boundary; field values, evidence and custom code stay Python. Worker
execution identity now also pins identity, survivorship and evidence modules,
besides the existing facade, STEPS and installed native binary. Runtime identity
changes intentionally; business output/assertion/policy hashes must not.

## Verified so far

- 60 focused native/public computation tests; later regressions bring identity
  tests to 14. Python mypy checks both adapters; Rust feature type checks pass.
- Complete Rust suite: 165 passes across 27 test groups.
- Real PostgreSQL 16 MergeStage and folded-stage acceptance: 63 passes (133.55s).
- Fresh complete MDM rerun at the correction: 648 passes (108.39s).
- Worker dependency qualification: 47 configured mapping tests, including all
  three new pinned modules. `doctor`: engine loads, 131 commands, no unresolved
  examples, stores unset for this standalone command.
- Three independent reviews: Standards, Spec and GoF; future-operand eager
  interpretation found, fixed with red/green public regressions, and independently
  rechecked against baseline. No remaining findings; see REVIEW.md.

Full maintained suite completed in 35m06s: 2,828 passed, one existing xfail,
one failure in the future-expiry regression. That long-running process had
loaded the adapter before its correction; the fresh full MDM rerun at the
committed correction passed all 648 tests, including that failure. Installed
bundle acceptance in the broad run used correction commit bf2278e3. Final
uncontended timings and post-rebase upstream checks remain pending.

## Qualification method

`scripts/dev/qualify_configured_merging.py` loads the exact pre-port Python
snapshot `e4be301962e0c2c1b6ab6efc0eb500747b7c718e` as a test-only oracle. It
compares seeded field/profile policies and identity histories, including expected
conflicts, then runs both implementations in separate processes with fresh
PostgreSQL 16 stores and restricted roles. Commits and lost-ack retries use the
same assertions, decisions, identity ids, run, policy and checkpoint. It compares
projection hashes and stored request/policy/generation receipts. Entity hashes
include losing-identity alias bodies. Three fresh commit/retry samples and three
pure-computation samples are reported per mode, plus whole-process peak RSS.

The workload pairs independent identities with two source claims each. Synthetic
policies/values include large integers, floats, booleans, Unicode, authorized
clears, unknown times, age limits, profile values and conflicting overrides in
the separate parity cases. Full physical performance samples contain no profile
or relationship workload; those behaviors are covered by the acceptance suite.
`--limit` is 2..600; records plus binds and merges must stay inside the existing
1,000-decision batch limit. A 1,000-record attempt correctly failed `Unbounded
batch` at the unchanged MergeStage entry gate.

Measurements taken while broad tests ran showed substantial timing variation;
those observations do not establish full-path performance. Final measurements
will run after the suites finish. No production corpus or deployed-path
qualification is claimed. Further native work includes source-history folding
and canonical comparison/materialization where measured costs justify it;
custom rules remain Python and database transaction authority remains enforced.

## Skill impact

Only `skills/data-platform/SKILL.md` gained an implemented responsibility note.
Reading and combination interfaces/bounds/verification did not change; onboarding,
rule qualification, approval and activation procedures did not change. Shared
skill edits passed the repository overlap guard. Operational examples remain the
existing commands and are checked by doctor and installed-bundle acceptance.
