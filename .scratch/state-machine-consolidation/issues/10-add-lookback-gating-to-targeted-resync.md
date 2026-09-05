Type: task
Status: open

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

- [ ] `targeted-resync`'s cik-scoped resync respects every existing and new
      lookback flag, via the single shared gate — no second, parallel
      lookback check added.
- [ ] Full-history override (`0`) still works for debug purposes.
- [ ] New tests pass; full `tests/unit/` suite green, no regressions.
- [ ] `/gof-refactor-reviewer` consulted before editing
      `warehouse_orchestrator.py` (repo hard rule).
- [ ] `/code-review` (Standards, Spec, GoF) run before this ticket's PR is
      considered ready.
