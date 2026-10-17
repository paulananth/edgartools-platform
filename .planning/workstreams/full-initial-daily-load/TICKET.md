# Initial and daily SEC, GLEIF and OpenFIGI load

Operator scope: populate initial Rules, MDM and RDM from existing local data;
define the full-load and daily sequences. Silver is excluded. No new provider
requests or production deployment are authorized. Bookkeeping and the Change
Journal begin empty and record real work as it runs.

Ruling, same session: "always load everything from source". The first plan
incorrectly interpreted this as forced daily reprocessing. The operator then
clarified: daily runs use the Change Journal to process changed data only.
The current rule is full-source enumeration with normal Journal filtering;
`--all` is reserved for an explicit forced replay.

- [x] Reconcile current captures, source registration, target support and shared store contents. Nine sources, thirteen Dataset Contracts; only Company declares acquisition authority; current source-owned mastering targets are incomplete. Shared stores were empty before this seed (2026-10-16 20:57 ET).
- [x] Seed committed Rules versions and restore the three existing published RDM code sets through their normal lifecycle, with exact pin equality and retained authorization. Saved 12 draft Rules versions. Restored 3 published version-1 reference sets through RDM draft/approve/publish using the operator's actual load request; every canonical hash equals its committed pin. Metadata identifies local restoration rather than pretending to recreate original publication timestamps. Private drafts, published artifacts and `seed-report.json` retained under `~/.local/share/edgartools/shared-source-loads/initial-20261016/`; backups taken before seeding (2026-10-16 20:57 ET).
- [x] Document initial and daily dependency order, full-population scope, completeness checks and current blockers. The initial forced-selection interpretation was corrected after the operator's Journal clarification: complete source enumeration, selected/skipped accounting and normal Journal filtering in the guide and both agent files (2026-10-16 21:01 ET).
- [x] Verify loaded reference pins and Rules status, preserve MDM/operational state, and review Standards, Spec and GoF applicability. Repeated seed reuses the same versions; 333 codes, 333 labels, 617 crosswalks, 5 usage rows and 6 hints retained. MDM has 0 entities/registered datasets; Bookkeeping and Journal remain empty. Three pin checks pass; full-selection check retains all three invented inputs without querying the skip ledger; `--all` parses. Agent rules agree; whitespace and overlap checks pass (2026-10-16 20:57 ET).
- [ ] ~~Execute full MDM mastering~~ deferred pending supported registration/run paths and unfinished OpenFIGI onboarding; do not bypass acquisition authority or substitute proof helpers.
- [x] Cross-check Journal selection and post-merge records. All 12 existing Company/Person selection and real PostgreSQL Journal-worker tests pass in 13.03 s: unchanged repeat selects none, one changed file selects one, meaningful shared-input changes select dependent files, forced replay selects all, receipts survive retries. The live shared Journal still has 0 events; initial source processing is not yet recorded (2026-10-16 21:01 ET).
- [x] Consolidate the initializer and corrected daily guide for one PR. The combined branch is current with origin/main; affected testmon verification passed 17 tests in 84.12 s, with 12 unchanged Journal cases deselected after their preceding passing run. Rechecked Standards, Spec and GoF on the combined diff; no new issues found. Shipping and Claude handoff remain separate from the deferred full MDM load (2026-10-17 07:25 ET).
- [x] Learning → skill: AGENTS.md and CLAUDE.md now distinguish complete source coverage from Journal-selected processing; normal initial/daily runs omit `--all`. The runtime and skills already support this; no runtime or skill code changed (2026-10-16 21:01 ET).

## Standards

Fresh branch/worktree; normal Rules and RDM APIs, private credentials and
artifacts, public counts only. No provider request, production write, source
rule change, matching-rule activation or MDM authority bypass. Exact pin and
database read-back checks verify these data operations; no application code changed.

## Spec

Both initial and daily discovery cover whole available deliveries, never a
cohort. The Journal selects unprocessed/changed files and changed processing
dependencies; zero selected files starts no mastering run. Initial Rules and
RDM seed is complete. Full MDM replay
is incomplete for the declared registration, mastering-target and OpenFIGI gaps;
no source was silently dropped to claim success. Bookkeeping and Journal are
empty now and retain real work evidence once loading starts. Silver is excluded.

## GoF

Reviewer skill is available. No production code, schema or processing interface
changed; design-pattern refactoring is inapplicable to the documentation and
reference restoration. Existing store APIs were used without new abstractions.
