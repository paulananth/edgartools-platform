Type: research
Status: resolved

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

**Two different root causes, not one.** Full detail, per-table, at
[research/03-empty-source-tables-investigation.md](../research/03-empty-source-tables-investigation.md).

**`sec_subsidiary_evidence` and `sec_auditor_report_evidence` (HAS_PARENT_COMPANY's and
AUDITED_BY's primary sources) — a real, close-to-shippable gap, flagged prominently:**
real, working, tested parsers exist (`edgar_warehouse/application/subsidiary_exhibits.py`,
`edgar_warehouse/application/auditor_evidence.py`, both from commit `d20cad81`,
2026-07-16) and are correctly wired into the `ingest-relationship-sources` command's
dispatch in `warehouse_orchestrator.py` — but **nothing in the codebase has ever produced a
manifest entry of the required `kind` for either one.** The only large-scale
candidate-discovery pipeline that exists (`edgar_warehouse/application/
relationship_bulk_load.py`, which drove release-readiness Ticket 20's real production
"TECHNICAL PASS" on 2026-07-25) covers exactly three document-type families —
`thirteenf`/`proxy`/`item_502_8k` — with **zero** mentions of subsidiary/auditor/EX-21/EX-8/
PCAOB anywhere in its 1,587 lines. Confirmed independently by release-readiness Ticket 35
(all 14 Snowflake graph generations ever produced show zero `HAS_PARENT_COMPANY`/`AUDITED_BY`
edges, ever) and by Tickets 22/23's own resolution text ("production [candidate] closure
remain[s] Ticket 20 execution evidence" — deferred to a step that never covered them). The
parser/write half of the pipeline is done; the discovery/fetch half was never built. This is
the actionable finding this ticket exists to surface.

**`sec_accounting_flag` (AUDITED_BY's fallback) — not a gap, a confirmed structural SEC-API
limitation with an open decision ticket.** The writer (`parsers/financials.py::parse_entity_facts`
+ `parsers/accounting_flags.py::backfill_accounting_flags`) is real, wired into
`bootstrap-fundamentals --mode entity-facts` (part of `load_history`'s Stage 1B), and **has
run in prod** — confirmed twice, independently (fix-pipelines EDGE-10, 2026-07-13; and
release-readiness Ticket 42's live single-CIK smoke test, 2026-07-29) — both times finding the
SEC companyfacts aggregate API never surfaces the 4 auditor-DEI XBRL concepts
(`AuditorFirmId`/`AuditorName`/`AuditorLocation`/`IcfrAuditorAttestationFlag`) for any filer,
for any company. Release-readiness Ticket 92 (`Status: open`) already tracks deciding an
alternative source (per-filing XBRL instance parsing, a different SEC endpoint, or decoupling
forensic scores from needing an auditor-DEI base row) — not duplicated by this ticket.

**Point 4 (migration 010's retirement columns):** `sec_accounting_flag` got
`valid_from`/`valid_to`/`is_current` in the same migration as `sec_financial_fact` because it's
the company-facts acceptance pipeline's other declared `required_producer` (change-propagation
Ticket 33's own Answer) — a deliberate schema-parity decision across two tables in the same
required-producer family, made independently of and unrelated to whether the table held rows
at the time. Does not indicate anyone expected it to already be populated; does not contradict
the structural-gap finding above.
