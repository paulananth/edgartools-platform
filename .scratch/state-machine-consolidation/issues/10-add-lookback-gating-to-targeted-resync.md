Type: task
Status: resolved (2026-09-06)

**Resolution:** `targeted-resync`'s cik-scoped branch now filters
`submissions_orchestrator`'s candidate accessions through
`_configured_parser_accessions` (same gate every bulk loader uses) before
looping `_run_accession_resync` -- both form-type eligibility and every
per-family lookback window (ownership, item-502, item-202, proxy,
13F, ADV) are now honored in one pass, no second/parallel lookback check.
`edgar_warehouse/cli.py`'s `targeted-resync` subparser gained all 7
lookback flags; `_add_fundamentals_lookback_args` gained a `default_years`
parameter so this command can default every family to `0`/full history
(its own debug-purpose default, confirmed via a user check-in) while every
existing bulk-loader caller keeps its implicit 2-year default unchanged.
Two product decisions, both confirmed via a check-in before implementing
rather than assumed: (1) route everything through the shared gate as
written -- a CIK-scoped resync now only ever touches configured-parser-form
accessions (ownership/ADV/proxy/13F/item-502/202 8-K); other form types
(10-K/10-Q/etc.) are no longer resynced via this path at all, a deliberate
accepted capability change, not a bug; (2) full history (`0`) is the
default for every family on this command specifically.

**Deliberately not wired:** `filing_lookback_years` (bounds
`sec_company_filing` discovery itself, a different axis than the
per-family artifact/parse lookback this ticket's "What to build" named).
`submissions_orchestrator` has no plumbing for any lookback kwarg at all,
and `_resolve_filing_lookback_years`'s own default is already `0`
(full history, opt-in-only) -- identical to what this command already
does without any wiring. The only real gap left is an explicit
`--filing-lookback-years` override for an advanced operator narrowing a
single-company resync's own bronze discovery; out of this ticket's named
scope, logged here rather than silently dropped.

Tests: `tests/unit/test_targeted_resync_lookback_gating.py` (new -- proves
out-of-window exclusion, the `0`/full-history override, the gate's own
2-year default when a caller omits the keys entirely, and both CLI-default
assertions) plus a regression fix to
`tests/unit/test_targeted_resync_accession_conflict_isolation.py` (its
`_FakeDb`, now shared by both files, needed a real `get_filing` once the
cik branch started calling `db.get_filing` for the first time). Full
`tests/unit` + `tests/architecture` suite green: 1564 passed, 5 skipped.
`/gof-refactor-reviewer` consulted before editing both `cli.py` and
`warehouse_orchestrator.py` (repo hard rule); `/code-review` (Standards,
Spec, GoF) run before this PR -- Standards' one real finding (duplicate
`_FakeDb` test class) fixed by consolidating into one shared, parameterized
class; GoF found nothing to fix (the pre-existing 5-copy ownership/item-502
argparse duplication was examined and correctly left alone -- all 4 prior
copies were introduced together in one commit, no independent
repeated-change evidence yet).

**Spawned by:** [Ticket 08 — Decide fate of MDM Pipeline Machine heads](08-decide-fate-of-mdm-pipeline-machine-heads.md)'s widened resolution (2026-09-05).
**Related:** [fundamentals-lookback-years spec](../../fundamentals-lookback-years/spec.md) — sequencing this ticket after that spec's implementation is a soft preference, not a hard block (see "What to build" below).

## Question

Not a decision — the decision is already made (Ticket 08: `targeted-resync`
stays, as a single-company debug/resync tool, but must honor the same
date-range lookback gates as every bulk loader, even though it only ever
targets one CIK at a time). This is the implementation.

**Confirmed gap:** `warehouse_orchestrator.py`'s `targeted-resync` handler,
`scope_type == "cik"` branch, calls `_run_accession_resync` over **every**
accession `submissions_orchestrator` returns for that CIK — no
`ownership_lookback_years`, `item_502_lookback_years`, `filing_lookback_years`,
or (once it lands) `fundamentals_lookback_years`/its per-family overrides are
applied at all. A single-CIK debug resync today always processes full
history, regardless of what every other loader's lookback flags say.

## What to build

Route `targeted-resync`'s per-accession selection through the same shared
gate everything else uses — `_configured_parser_accessions`/
`_is_configured_parser_form` — rather than adding a second, parallel
lookback check. This is the same "one gate" principle the
fundamentals-lookback-years spec already established for the four newly-
bounded form families; wiring `targeted-resync` through the identical gate
means it inherits every lookback control (existing and new) in one pass,
which is why sequencing this after that spec lands is preferable, though
not required — the existing `ownership_lookback_years`/`item_502_lookback_years`
gap is real and fixable independently if this ticket is picked up first.

Specifics to work out during implementation (not pre-decided here):

- Whether `targeted-resync`'s CLI already exposes `--ownership-lookback-years`
  etc. as accepted arguments (confirm via `edgar_warehouse/cli.py`'s
  `targeted-resync` subparser) or whether they need adding there too,
  matching the other lookback-aware subcommands.
- Whether `0` (full history) should be the resync default given its debug
  purpose (a developer resyncing one company to investigate an issue may
  often want full history) — or whether it should default the same as the
  bulk loaders and require an explicit override for full history. This is
  a real product decision, not purely mechanical — resolve via a quick
  `/grilling` check-in rather than assuming either way.
- Whether this changes `force`'s existing `default=True` behavior at all
  (it shouldn't — `force` and lookback-year bounding are orthogonal:
  force controls whether already-captured accessions get re-fetched, the
  lookback gate controls which accessions are even considered).

## Tests

Extend the same seam the fundamentals-lookback-years spec uses
(`tests/unit/test_ownership_lookback.py`'s `TestConfiguredParserAccessionsLookback`
family, or a sibling test class in the same file) with a case proving
`targeted-resync`'s cik-scoped branch now excludes out-of-window accessions
the same way `daily-incremental`/`bootstrap-next` already do, and a case
proving an explicit `0`/full-history override still resyncs everything —
matching this repo's established pattern of testing the real function
directly rather than re-implementing its logic in the test.

## Acceptance

- [x] `targeted-resync`'s cik-scoped resync respects every existing and new
      lookback flag, via the single shared gate — no second, parallel
      lookback check added.
- [x] Full-history override (`0`) still works for debug purposes.
- [x] New tests pass; full `tests/unit/` suite green, no regressions.
- [x] `/gof-refactor-reviewer` consulted before editing
      `warehouse_orchestrator.py` (repo hard rule).
- [x] `/code-review` (Standards, Spec, GoF) run before this ticket's PR is
      considered ready.
