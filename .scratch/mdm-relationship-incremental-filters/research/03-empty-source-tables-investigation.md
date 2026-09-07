# 03 — Why are sec_subsidiary_evidence / sec_auditor_report_evidence / sec_accounting_flag empty?

Read-only investigation for
[Ticket 03](../issues/03-investigate-empty-has-parent-company-audited-by-source-tables.md).
No code changed, no decisions made.

## Headline

Two different root causes, not one:

- **`sec_subsidiary_evidence` and `sec_auditor_report_evidence`** (HAS_PARENT_COMPANY's
  primary source, AUDITED_BY's primary source): **real, working parsers exist and are wired
  into a real ingest command's dispatch — but the candidate-discovery/fetch half of the
  pipeline that would feed that dispatch real inputs was never built.** The write path has
  literally never received a single input in any environment, ever. **This is the
  actionable gap** — see "What would need to run" below.
- **`sec_accounting_flag`** (AUDITED_BY's fallback): a real writer exists, is wired into a
  real CLI command, and **has run successfully in prod** (2026-07-29 smoke test) — but the
  specific SEC data source it reads from structurally cannot supply the 4 auditor-DEI XBRL
  concepts it needs, for any filer. This is a live-confirmed, structural SEC-API limitation,
  already root-caused twice independently (fix-pipelines EDGE-10, release-readiness ticket
  42) and left with an explicit, still-open decision ticket (release-readiness Ticket 92)
  for an alternative source. Not "never run" — "ran correctly, source is insufficient."

---

## Table 1: `sec_subsidiary_evidence` (HAS_PARENT_COMPANY primary source)

**Writer exists:** yes, real and non-trivial.
- Parser: `edgar_warehouse/application/subsidiary_exhibits.py::parse_subsidiary_exhibit` —
  a deterministic SEC Exhibit 21 / Form 20-F Exhibit 8 subsidiary-list parser (BeautifulSoup
  HTML parsing, explicit-zero detection, row-locator preservation).
- Silver write: `SilverDatabase.merge_subsidiary_evidence` (`edgar_warehouse/silver_store.py:2533`),
  called via `ingest_subsidiary_parse_result` (`subsidiary_exhibits.py`).
- Schema: DDL in `silver_store.py:307`, protected-table policy in `silver_protection.py:154`,
  Snowflake landing schema (`infra/snowflake/sql/bootstrap/11_silver_landing_schema.sql:632`),
  dbt silver passthrough model, `EDGARTOOLS_SOURCE` export comment describing it as "Passthrough
  from silver sec_subsidiary_evidence" (`01_source_stage.sql:423`).

**Wired into a dispatch path:** yes.
`edgar_warehouse/application/warehouse_orchestrator.py`'s `ingest-relationship-sources`
command (real CLI command, `edgar_warehouse/cli.py:1357`, real Step Functions state usage —
`infra/scripts/deploy-aws-application.sh` wires it into the ADV/relationship-source stages)
dispatches on a manifest entry's `"kind"` field. `kind == "sec_subsidiary_exhibit"` calls
`parse_subsidiary_exhibit` then `ingest_subsidiary_parse_result`
(`warehouse_orchestrator.py:2647-2663`). The code path is real, tested
(`tests/application/test_subsidiary_exhibits.py`), and would work if fed a real manifest entry.

**Never fed — this is the actual gap.** `ingest-relationship-sources` only ever *consumes* a
manifest; something else must *produce* one with a `"kind": "sec_subsidiary_exhibit"` entry
(accession, registrant CIK, document bytes, SHA-256, etc.). Grepped the entire repo for any
code that emits that manifest-entry kind: **zero producers exist.** The only two manifest
producers in the codebase (`adv_bulk_fetch.py`'s `build_source_manifest` for
`iapd_adv_bulk`/`iapd_firm_roster`, and `firm_roster_fetch.py`'s equivalent) never emit
`sec_subsidiary_exhibit`/`sec_auditor_filing`/`pcaob_firm_registry` kinds.

The one real, large-scale candidate-discovery pipeline that exists in this codebase for
feeding `ingest-relationship-sources` at production scale is
`edgar_warehouse/application/relationship_bulk_load.py` (1,587 lines, drives the
release-readiness "Ticket 20" strict relationship bulk load that reached a live
**TECHNICAL PASS in prod on 2026-07-25**, `.scratch/release-readiness/issues/
20-execute-required-relationship-production-bulk-load.md`). Its entire candidate-inventory
logic is built around exactly **three** document-type families:
`"thirteenf"`, `"proxy"`, `"item_502_8k"` (confirmed via every `for key in (...)` loop and
the `coverage_by_document_type` schema in that file) — mapping to `INSTITUTIONAL_HOLDS`,
`EMPLOYED_BY`, and `IS_INSIDER`/`EMPLOYED_BY` respectively. **Grepped the entire 1,587-line
file case-insensitively for "subsidiary", "auditor", "ex-21", "ex21", "ex-8", "pcaob" — zero
matches.** The strict bulk load that actually ran and passed in prod never enumerated a
single 10-K/20-F/40-F annual filing or Exhibit 21/8 attachment as a candidate. It could not
have produced any `sec_subsidiary_exhibit` or `sec_auditor_filing`/`pcaob_firm_registry`
manifest entries, regardless of outcome.

**Corroborating, independent evidence this never ran:**
- `.scratch/release-readiness/issues/35-promotion-criteria-graph-neighborhood.md` (a later,
  separate audit) queried all 14 tracked Snowflake graph generations
  (`NEO4J_GRAPH_MIGRATION.GRAPH_GENERATION`) for distinct `relationship_type` values on
  `MDM_GRAPH_EDGES`: only `MANAGES_FUND`, `EMPLOYED_BY`, `HOLDS`, `COMPANY_HOLDS`,
  `IS_INSIDER` have ever appeared, in any generation, ever. `HAS_PARENT_COMPANY` and
  `AUDITED_BY` have **never existed as an edge type in this graph's history at all** —
  consistent with their source tables never having received a candidate row in the first
  place. That ticket explicitly flagged root-causing this as "not attempted... flagging for
  a dedicated follow-up rather than guessing" — this investigation is effectively that
  follow-up.
- `.scratch/release-readiness/issues/06-define-full-chain-launch-gate.md` names
  `HAS_PARENT_COMPANY`/`AUDITED_BY` in its Stage 5 ("Relationship Source Completion... per-
  relationship-type accession-level source inventory/completion ledgers") as required, but
  the actual candidate-ledger implementation ticket
  (`.scratch/release-readiness/issues/16-implement-relationship-source-candidate-ledger.md`)
  has zero mentions of subsidiary/auditor either — the gate document names them as required;
  nothing that was actually built ever produced their candidates.

## Table 2: `sec_auditor_report_evidence` (AUDITED_BY primary source)

Identical shape to Table 1, same commit, same never-fed gap.

**Writer exists:** yes. `edgar_warehouse/application/auditor_evidence.py::parse_auditor_evidence`
(direct annual-filing Inline XBRL auditor-triplet parser plus a bounded audit-report/
signature-block fallback parser — real XML/HTML parsing, not a stub) and
`parse_pcaob_firm_registry` (PCAOB AuditorSearch/Form AP bulk snapshot parser). Silver write:
`SilverDatabase.merge_auditor_report_evidence` (`silver_store.py:2565`) via
`ingest_auditor_parse_result`; `merge_pcaob_firm_identities` for the firm-identity table.

**Wired into dispatch:** yes — same `ingest-relationship-sources` command,
`kind == "sec_auditor_filing"` (calls `parse_auditor_evidence`/`ingest_auditor_parse_result`)
and `kind == "pcaob_firm_registry"` (calls `parse_pcaob_firm_registry`/
`merge_pcaob_firm_identities`), both real branches in `warehouse_orchestrator.py:2664-2695`.

**Never fed:** identical reasoning as Table 1 — no manifest producer anywhere in the repo
emits `sec_auditor_filing` or `pcaob_firm_registry` kinds, and `relationship_bulk_load.py`'s
candidate inventory (the only pipeline that ever ran a real production bulk load) has zero
auditor/PCAOB coverage.

**Both parsers were built in one commit, together, and never touched again:**
`git log --oneline --follow` on both `subsidiary_exhibits.py` and `auditor_evidence.py`
shows exactly one commit each: `d20cad81` ("release: relationship production bulk-load
readiness (#135)", 2026-07-16). Neither file has been modified since. The commit's own PR
description lists release-readiness tickets 14/15/22/23 ("Define Parent-Company Source and
Parser Contract", "Define Auditor Evidence Ingestion Contract", "Implement SEC Subsidiary
Exhibit Ingestion", "Implement Auditor-Report Evidence Ingestion") — all four marked
`Status: resolved` in `.scratch/release-readiness/`. Tickets 22 and 23's own Resolution
sections both explicitly say the same thing, almost word-for-word: **"Production
[candidate/inventory] closure ... remain[s] ticket 20 execution evidence"** — i.e., the
parser/contract implementation was scoped as "done," with the actual production run of
real candidates through it deliberately deferred to Ticket 20. Ticket 20 then ran, passed
technically, and never touched these two document types at all (see Table 1's
`relationship_bulk_load.py` finding). The deferral chain never closed the loop.

**Already tracked, partially, in three places, none of which connected all the dots:**
1. `.scratch/silver-sharded-writes/issues/05-decide-rollout-sequencing-and-safety-gate.md`:
   "`sec_subsidiary_evidence`/`sec_auditor_report_evidence` have no confirmed caller in the
   codebase today" — correct conclusion, but scoped only to a sharding-safety question and
   didn't investigate *why* (that ticket only checked whether ordinary write-path code calls
   `merge_subsidiary_evidence`/`merge_auditor_report_evidence` directly, not whether the
   `ingest-relationship-sources` dispatch that *does* call them is ever fed).
2. `.scratch/release-readiness/issues/35-promotion-criteria-graph-neighborhood.md`: found the
   zero-graph-edges symptom, explicitly declined to root-cause it.
3. `docs/release-readiness/auditor-evidence-ingestion-contract.md` (the design doc, still
   live) even flags its own incompleteness: "The current lookup-only behavior and skip in
   `pipeline.py` cannot satisfy this contract" — acknowledging `_derive_audited_by`'s
   existing fallback-only behavior is a known-insufficient stopgap versus the full contract's
   vision (PCAOB Form AP corroboration, full firm-identity model, etc.), none of which have
   candidate-discovery code behind them yet.

None of the three duplicate this ticket's finding exactly (the specific "which document types
`relationship_bulk_load.py`'s inventory covers, and it's not these two" fact) — this
investigation is new, not a re-tread.

## What would need to run to populate Tables 1 and 2 (informational only — no decision made)

Per the contract docs (`docs/release-readiness/parent-company-source-parser-contract.md`,
`docs/release-readiness/auditor-evidence-ingestion-contract.md`), the missing piece for both
tables is the same shape of work: a **candidate-discovery/inventory step** that (a) enumerates
eligible annual filings (10-K/10-K/A/10-KT/20-F/40-F and amendments for auditor evidence; any
filing carrying an EX-21/EX-8 attachment for subsidiary evidence), (b) fetches the underlying
document bytes (already-existing bronze/SEC-fetch infrastructure could plausibly be reused —
not confirmed here), and (c) emits `ingest-relationship-sources` manifest entries of the
correct `kind`. For auditor evidence, a PCAOB AuditorSearch/Form AP bulk-download step (`kind:
pcaob_firm_registry`) is also needed for full firm-identity coverage per the contract, though
`parse_auditor_evidence` alone (direct iXBRL/report-parsing) could in principle populate
`sec_auditor_report_evidence` without it.

This is a **real, close-to-shippable gap**: the hard part (parsing) is already built and
tested; what's missing is wiring a discovery/fetch step (most likely a new
`relationship_bulk_load.py`-style document-type family, or a dedicated new command) that
builds the manifest these existing, working parsers already know how to consume.

## Table 3: `sec_accounting_flag` (AUDITED_BY fallback source)

**Writer exists, is wired, and has run in prod.** Two real code paths:
- `edgar_warehouse/parsers/financials.py::parse_entity_facts` builds `sec_accounting_flag`
  base rows from four DEI XBRL concepts (`AuditorFirmId`, `AuditorName`, `AuditorLocation`,
  `IcfrAuditorAttestationFlag`) parsed out of the SEC companyfacts aggregate API response.
- `edgar_warehouse/parsers/accounting_flags.py::backfill_accounting_flags` computes
  cross-period forensic scores (Beneish M-score, Altman Z-score, Piotroski F-score) from
  `sec_financial_derived` and upserts them onto existing `sec_accounting_flag` rows.

Both are wired into the real `bootstrap-fundamentals --mode entity-facts` CLI command
(`edgar_warehouse/application/commands/bootstrap_fundamentals.py`), which is itself wired
into `load_history`'s Stage 1B (`FetchEntityFacts`, per CLAUDE.md's Phased Pipeline section).

**Confirmed run in prod, twice, independently, with the identical structural finding both
times:**
1. `.planning/workstreams/fix-pipelines/phases/06-relationship-investigation-and-population/
   06-05-EDGE10-DISPOSITION.md` (2026-07-13): live-fetched Apple's real
   `data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json` directly and confirmed its `dei`
   facts section contains only 2 concepts total — none of the four auditor concepts the
   parser looks for are ever present. Confirmed on 3 unrelated large-cap filers (Apple,
   Microsoft, NVIDIA), with a clean control fact (`dei:EntityRegistrantName`, also
   `ix:nonNumeric`, present on every 10-K but unrelated to auditor data — also absent from
   all three companyfacts responses, ruling out an "auditor-specific" exclusion).
   **Disposed 2026-07-13 as EDGE-10: "EXCLUDED — source-coverage exclusion (structural SEC
   API limitation)"** (`.planning/workstreams/fix-pipelines/REQUIREMENTS.md:44`).
2. `.scratch/release-readiness/issues/42-decide-execute-fundamentals-backfill.md` (2026-07-29,
   over two weeks later, apparently independently): a real single-CIK smoke test against
   prod (CIK 320193, direct `aws ecs run-task`, real writes to canonical silver) reproduced
   the identical finding — `sec_financial_fact`/`sec_financial_derived` populated correctly
   (values verified to match Apple's real public 10-K exactly), but `sec_accounting_flag`
   stayed at 0 rows despite the task log falsely claiming `"accounting_flags_updated": 129`.
   Root-caused to the same structural gap (four auditor DEI concepts never present in
   companyfacts) plus a second, independent bug: `backfill_accounting_flags`'s `UPDATE`
   against zero matching rows doesn't raise in DuckDB, so its "updated" counter silently
   counted no-ops as successes (same masking-bug shape CLAUDE.md's INSTITUTIONAL_HOLDS
   5-whys already warns about).

**Not a "never run" gap — a "ran correctly, source is structurally insufficient" gap, with
an explicit, still-open decision ticket:** `.scratch/release-readiness/issues/
92-decide-f11-accounting-flag-data-source.md`, **Status: open** (not resolved, not
abandoned). It lays out three live candidate resolutions: (a) parse the four DEI concepts
from the 10-K's own per-filing XBRL instance document instead of the aggregated companyfacts
API, (b) find a different SEC endpoint/dataset that does surface these tags, or (c) decouple
the forensic-score writes from needing an auditor-DEI base row at all, letting
`backfill_accounting_flags` write its own base row keyed on `(cik, accession_number)` directly
from `sec_financial_derived`. None of the three has been chosen or implemented as of this
investigation.

## Point 4: why did sec_accounting_flag get valid_from/valid_to/is_current despite 0 rows?

`.scratch/change-propagation/issues/33-add-validity-interval-retirement-to-financial-facts.md`
(migration `010_company_facts_retirement_columns`, referenced throughout CLAUDE.md's "Migration
010 DuckDB commit-conflict" and "sec_financial_fact retirement publish-conflict" 5-whys
sections) answers this directly, in its own Answer section:

> Both `sec_financial_fact` and `sec_accounting_flag` gained `valid_from`/`valid_to`/
> `is_current`... — `sec_accounting_flag` included because **it's the family's other required
> producer** (a different Ticket 22 — change-propagation's own numbering, the company-facts
> acceptance-gate ticket, not release-readiness's identically-numbered subsidiary-exhibit
> ticket; confirmed via `COMPANY_FACTS_FLAG_PRODUCER_NAME = "sec_accounting_flag"` and
> `required_producers=("sec_financial_fact", "sec_accounting_flag")` in
> `edgar_warehouse/acquisition/company_facts_silver_acceptance.py`), and leaving only one of
> the two asymmetric was judged worse than treating both.

This was a **deliberate schema-parity decision**, not evidence anyone expected the table to
already hold data. `sec_financial_fact` and `sec_accounting_flag` are both "required
producers" of the same single-phase company-facts acquisition/acceptance pipeline (one
companyfacts JSON response can, in principle, produce rows for either or both tables) — the
migration's authors chose to add the retirement columns to both required producers uniformly
rather than leave `sec_accounting_flag` unretireable while its sibling table got full
retirement support, on the reasoning that an asymmetric schema across two tables in the same
required-producer family is a worse outcone than an unused column on an empty table. This
is fully consistent with, and does not contradict, Table 3's separate finding above (the
table was empty *at that time* for the unrelated structural companyfacts-API reason, not
because nobody expected it to ever have data — Ticket 92 is explicit that a real fix path
exists and is only pending a data-source decision).

## Note on a naming collision

Release-readiness's Ticket 22 ("Implement SEC Subsidiary Exhibit Ingestion") and
change-propagation's Ticket 22 (the company-facts-retirement producer ticket cited in Point 4
above) are two *different* tickets that happen to share the number 22 because they live in
separate wayfinder maps with independent numbering. Neither this file nor the two source
tickets conflate them, but a future reader grepping only for "Ticket 22" across `.scratch/`
should check the map directory, not just the number.
