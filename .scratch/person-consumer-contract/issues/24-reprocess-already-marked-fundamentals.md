# Give per-filing fundamentals a force/reprocess path

Type: task
Status: resolved (2026-09-21)
Blocked by: none — but **blocks the ticket 10 re-export**

## Resolution

Done on `claude/person-ticket-24`. `--force` on `bootstrap-fundamentals` now
reaches all three modes.

| Item | Change |
|---|---|
| 1 | `workflows/fundamentals_ingest.py`: new `_drop_already_processed(filings, source, mode, metrics, force)` replaces the two identical marker-lookup blocks. With `force=True` it never queries `sec_fundamentals_processed_accession`, records `filings_forced`, emits `fundamentals_force_reprocess`. Default path unchanged byte-for-byte. |
| 2 | `commands/bootstrap_fundamentals.py` passes `force=bool(getattr(args, "force", False))` to per-filing (and 13F — see below); `cli.py` `--force` help now describes all three modes |
| 3 | **Version-awareness weighed and not taken.** A `parser_version` column on the marker would make "reprocess what an old parser wrote" a normal run, matching the ownership family — but it is a landing-zone schema change across `silver_schema.py`, `11_silver_landing_schema.sql`, `test_silver_schema_snapshot.py` and the marker writer, for a table with no live migration path today. The explicit repair flag is the smaller change and is the pattern the SEC-idempotency rule prescribes. Recorded in the helper's docstring so the next parser correction finds the reasoning. |
| 4 | Skip by default, reprocess only on `--force`: `test_force_defaults_off_so_skip_behaviour_is_unchanged` |

**Scope extension, deliberate.** The ticket's "what to do" named
`run_bootstrap_fundamentals_per_filing` only; the same marker-lookup block
existed verbatim in `run_bootstrap_thirteenf` (both born in `1d7dcba0`,
edited in lockstep in `a52e3066`), so `force` is threaded through 13F as
well. One flag, one meaning across per-filing and 13F; the ticket's own
framing ("the general 'a parser got better' gap, not proxy-specific") is why.
`run_bootstrap_entity_facts` keeps its own version-gated mechanism — a
different algorithm (`has_companyfacts_at_version` + watermark + carve-out),
not a third copy of this block.

**Proof.** `tests/unit/test_fundamentals_incremental_scoping.py` +3: force
re-parses a marked accession without consulting the marker table and
re-marks it (`mark_fundamentals_accession_processed` runs unconditionally,
so re-marking lands at a new `parse_sequence` — exactly what ticket 23's
second unit test collapses on); force defaults off; 13F force skips the
lookup. Fundamentals suites: 128 passed.

**Review.** Three-axis: Standards — one should-fix (`filings_forced` was
not seeded at 0 like every sibling metric, so the run-summary key set varied
by flag — seeded in both dicts, test asserts 0), one nit (the shared helper
emits `fundamentals_force_reprocess` for the 13F path too, where the file's
other events are `thirteenf_*` — left as is, the event carries `mode=`;
noted); confirmed the Step Functions stage builder passes no `--force`, so
the flag stays operator-only. Spec — two should-fix (item 3's judgment
unrecorded — now in the docstring and above; the 13F extension unattributed
— now attributed above). GoF — leave it, the extraction is earned by the two
blocks' lockstep history and correctly stops short of folding entity facts
into it.

Ticket 10's re-export sequence is recorded on
[ticket 10](10-fix-proxy-executive-name-parser-leak.md).

## Question

Nothing to decide; raised by the Standards axis of ticket 10's code review
and already anticipated by research 12 F1.

A parser fix does not reach data that is already ingested.
`run_bootstrap_fundamentals_per_filing` skips work purely by accession:
`_get_processed_accessions` reads `sec_fundamentals_processed_accession`,
whose key is `(mode, accession_number)` with **no `parser_version` column**
(`edgar_warehouse/application/workflows/fundamentals_ingest.py:113-133`,
`:221-227`; `edgar_warehouse/silver_schema.py:344`). The function takes no
`force` parameter, so there is no operator lever at all — unlike
`run_bootstrap_entity_facts`, which has had one since Ticket 04
(`fundamentals_ingest.py:337-348`), and unlike the ownership family, which is
genuinely version-gated (`warehouse_orchestrator.py:3134-3155` checks
`has_successful_ownership_parse(..., parser_version=...)`).

Consequence: [ticket 10](10-fix-proxy-executive-name-parser-leak.md) bumped
`PARSER_VERSION` to `"2"`, and that bump is **inert**. The fix applies to
newly-ingested DEF 14A filings only; the ~14,755 already-published
`sec_executive_record` rows stay as they are until someone reprocesses them.

## What to do

Follow the established pattern rather than inventing one:

1. Thread `force: bool = False` through
   `run_bootstrap_fundamentals_per_filing`, skipping the
   `_get_processed_accessions` filter when set — mirroring
   `run_bootstrap_entity_facts`.
2. Pass it from `application/commands/bootstrap_fundamentals.py:173` the way
   the other two modes already do (`:190`, `:240`:
   `force=bool(getattr(args, "force", False))`).
3. Prefer version-awareness over a blunt flag if it is cheap: a
   `parser_version` column on `sec_fundamentals_processed_accession` would
   make "reprocess what an old parser wrote" a normal run rather than an
   operator action, matching the ownership family.
4. CLAUDE.md's SEC-idempotency rule stands: skip by default, re-fetch only on
   an explicit `--force`.

Note this is **shared** with [ticket 19](19-capture-ownership-parser-evidence.md)
and with any future parser correction — it is the general "a parser got better,
now re-read what it already read" gap, not a proxy-specific one.

Resolved when a fixed parser can be applied to an already-marked accession
without hand-editing bookkeeping rows.
