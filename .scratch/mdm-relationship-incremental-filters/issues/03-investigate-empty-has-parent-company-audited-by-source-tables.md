Type: research
Status: claimed

**Spawned by:** [Ticket 01](01-confirm-incremental-filtering-status-and-data-volume.md)'s live-queried finding: `HAS_PARENT_COMPANY`'s primary source (`sec_subsidiary_evidence`) and `AUDITED_BY`'s both sources (`sec_auditor_report_evidence`, `sec_accounting_flag`) are all 0 rows in `EDGARTOOLS_PROD.EDGARTOOLS_SILVER` (live-verified with a direct `COUNT(*)`, not assumed) — meaning both relationship types currently derive nothing from their documented "bounded" primary code path and fall through to their fallback branch on every single call.

## Question

Is this genuine — these tables really have no matching data yet, awaiting a future filer/parser that hasn't shipped — or is it the same class of gap CLAUDE.md already documents multiple times elsewhere (`ShardedSilverReader._TABLES` omitting a table, `TICKER_REFERENCE` never populated because `seed-universe` had never successfully run, `EXCLUDED_OPERATIONAL_TABLES` never actually reaching canonical silver): a real ingestion/parser/write path that was built but never wired up, or wired up but never successfully run against prod?

Investigate:
1. Does anything in the codebase actually write to `sec_subsidiary_evidence`, `sec_auditor_report_evidence`, or `sec_accounting_flag`? Find the writer (parser, batch script, whatever populates these tables) and confirm whether it has ever run successfully in prod, or whether it doesn't exist/was never wired into any command.
2. If a writer exists but never ran: what would need to run (which CLI command, which form type's parser) to populate it, and is there a known blocker (unimplemented parser, a form type not yet in scope, an unwired dispatch)?
3. If no writer exists at all: is this a genuinely unimplemented feature (a parser for subsidiary-evidence/auditor-report/accounting-flag data that was scoped but never built), and if so is that already tracked somewhere (check `.scratch/` for an existing ticket/map before assuming it's undocumented)?
4. Cross-check `sec_accounting_flag` specifically against CLAUDE.md's own schema-conventions/retirement-columns history — it's mentioned there in the `sec_financial_fact` retirement-columns migration (Ticket 33) as a sibling table that got the same `valid_from`/`valid_to`/`is_current` columns, which is odd for a table with zero rows; confirm whether that migration's own context sheds light on whether this table was ever expected to be populated yet.

Read-only investigation — no code changes, no decisions about what (if anything) to build. Use `/research` per this map's workflow.

## Answer

_(pending)_
