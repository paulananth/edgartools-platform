# Give per-filing fundamentals a force/reprocess path

Type: task
Status: open
Blocked by: none — but **blocks the ticket 10 re-export**

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
