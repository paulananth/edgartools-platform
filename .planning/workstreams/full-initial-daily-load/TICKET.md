# Initial and daily SEC, GLEIF and OpenFIGI load

Operator scope: populate initial Rules, MDM and RDM from existing local data;
define the full-load and daily sequences. Silver is excluded. No new provider
requests or production deployment are authorized. Bookkeeping and the Change
Journal begin empty and record real work as it runs.

Later ruling, same session: "always load everything from source". Both initial
and daily processing cover every record of the complete available delivery;
the default processed-file skip must be disabled, with idempotent writes.

- [x] Reconcile current captures, source registration, target support and shared store contents. Nine sources, thirteen Dataset Contracts; only Company declares acquisition authority; current source-owned mastering targets are incomplete. Shared stores were empty before this seed (2026-10-16 20:57 ET).
- [x] Seed committed Rules versions and restore the three existing published RDM code sets through their normal lifecycle, with exact pin equality and retained authorization. Saved 12 draft Rules versions. Restored 3 published version-1 reference sets through RDM draft/approve/publish using the operator's actual load request; every canonical hash equals its committed pin. Metadata identifies local restoration rather than pretending to recreate original publication timestamps. Private drafts, published artifacts and `seed-report.json` retained under `~/.local/share/edgartools/shared-source-loads/initial-20261016/`; backups taken before seeding (2026-10-16 20:57 ET).
- [x] Document initial and daily dependency order, full-population scope, completeness checks and current blockers. `docs/initial-and-daily-source-load.md` covers full-source initial and daily runs, complete worklist accounting, forced selection and source-specific cadence. Existing contradictory skip-default text was corrected in both agent guides (2026-10-16 20:57 ET).
- [x] Verify loaded reference pins and Rules status, preserve MDM/operational state, and review Standards, Spec and GoF applicability. Repeated seed reuses the same versions; 333 codes, 333 labels, 617 crosswalks, 5 usage rows and 6 hints retained. MDM has 0 entities/registered datasets; Bookkeeping and Journal remain empty. Three pin checks pass; full-selection check retains all three invented inputs without querying the skip ledger; `--all` parses. Agent rules agree; whitespace and overlap checks pass (2026-10-16 20:57 ET).
- [ ] ~~Execute full MDM mastering~~ deferred pending supported registration/run paths and unfinished OpenFIGI onboarding; do not bypass acquisition authority or substitute proof helpers.
- [x] Learning → skill: the operator's full-source ruling is in AGENTS.md and CLAUDE.md under Shared local data, with the sequence pointer; no skill code changed. Full processing, capture acquisition and idempotent persistence are separate concerns (2026-10-16 20:57 ET).

## Standards

Fresh branch/worktree; normal Rules and RDM APIs, private credentials and
artifacts, public counts only. No provider request, production write, source
rule change, matching-rule activation or MDM authority bypass. Exact pin and
database read-back checks verify these data operations; no application code changed.

## Spec

Both initial and daily runs cover whole available deliveries, never a cohort
or changed-file subset. Initial Rules and RDM seed is complete. Full MDM replay
is incomplete for the declared registration, mastering-target and OpenFIGI gaps;
no source was silently dropped to claim success. Bookkeeping and Journal are
empty now and retain real work evidence once loading starts. Silver is excluded.

## GoF

Reviewer skill is available. No production code, schema or processing interface
changed; design-pattern refactoring is inapplicable to the documentation and
reference restoration. Existing store APIs were used without new abstractions.
