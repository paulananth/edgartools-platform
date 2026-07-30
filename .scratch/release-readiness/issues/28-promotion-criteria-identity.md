# 28 — Product-ready promotion criteria for Identity / ticker-CIK (F1)

Type: grilling
Status: resolved
Blocked by:

## Question

What is the complete, product-ready set of acceptance criteria that must all pass before
Identity (ticker/CIK) is promoted from Partial to Covered in the coverage matrix? Concrete
platform surface per the matrix footnote: `TICKER_REFERENCE`; gold `COMPANY`/`dim_company`;
silver `sec_company`, `sec_company_ticker`; MDM `mdm_company` (CIK, canonical name,
ticker/exchange, tracking status). Note (2026-07-29): `COMPANY` was just enriched with MDM
`entity_id`/`display_name`/`tracking_status`/`parent_company_entity_id` via the
unified-company-dimension effort (`.scratch/unified-company-dimension/`) — ground this
checklist in the *current* post-enrichment schema, not the pre-enrichment one ticket 25 was
originally scoped against.

Write this as a numbered list of criteria (coverage breadth across the tracked/active
universe, ticker↔CIK join correctness and collision handling, staleness/freshness bounds,
MDM/warehouse identity agreement, no fabricated/placeholder rows), each with a concrete,
checkable acceptance query or procedure, following the exact method and rigor of
`erdp-coverage-promotion` tickets 03–06 — grounded in real schema, cross-checked against
ticket 27's ER-skill survey findings for this product, adversarially stress-tested for what a
naive checklist would miss.

## Progress (2026-07-29)

Started grilling and found a major, unanticipated gap before drafting any criteria:
`EDGARTOOLS_GOLD.TICKER_REFERENCE` and its upstream `EDGARTOOLS_SOURCE.TICKER_REFERENCE` are
both 0 rows in prod, and per ticket 27's survey, ticker/name resolution is the single most
load-bearing capability across all 9 ER skills — every one of them uses it as the primary
input. Rather than draft a checklist around a table that may not be the real ticker source at
all (the only populated ticker data lives on `MDM_COMPANY_ENTITY.ticker`, ~8% coverage, a
completely different pipeline), spun this off as a dedicated root-cause ticket — [Root-cause
the empty TICKER_REFERENCE pipeline](40-root-cause-empty-ticker-reference-pipeline.md) — so
this ticket's checklist can be written against the actual intended canonical ticker source once
that's known, not a guess. Re-blocked from 27 (resolved) to 40 (open).

## Progress (2026-07-29, ticket 40 resolved — unblocked)

Ticket 40 resolved with a clear, evidence-backed answer: **`TICKER_REFERENCE`'s 0 rows is a
genuine, isolated export-wiring bug** (gated to only fire on the one-time `seed-universe`
command, never on `daily-incremental`/`load_history`/`gold-refresh`) — **but the underlying
ticker data is not missing or broken**. Silver `sec_company_ticker` (8,056 distinct CIKs,
refreshed continuously, fed from `edgartools`'s own SEC `company_tickers.json` fetch) is the
real, healthy, canonical root source; `MDM_COMPANY_ENTITY.ticker` is a derived copy of it (via
`mdm/universe.py`'s `bulk_upsert_universe`), not an independent pipeline. The claimed "third
source," silver `sec_tracked_universe`, does not exist in real deployments — confirmed a dead
legacy table (`ShardedSilverReader` comment "legacy table; best-effort";
`test_silver_store_counts.py` asserts it's always 0) — the actual code path always falls back
to `sec_company_ticker JOIN sec_company_sync_state`.

Separately, ticket 40 confirmed the low ~8-10% ticker-population figure (on
`MDM_COMPANY_ENTITY.ticker`, on silver `sec_company_ticker`, and on a direct cross-reference
against SEC's own official `company_tickers.json`) is **not a bug** — it matches SEC's own
ground truth for this platform's exact 26,300-row active/tracked population almost exactly
(9.8% on all three). The tracked/active universe is 88.9% `entity_type='other'` (insiders,
investment advisers, broker-dealers, trusts — not equity issuers), so a low aggregate ticker
rate is structurally expected; `entity_type='operating'` alone matches SEC's ticker file at
72.9%.

**Implication for this ticket's checklist:** write criteria against silver `sec_company_ticker`
as canonical (with `MDM_COMPANY_ENTITY.ticker` as an acceptable derived read-path, not a
second source of truth), and scope any coverage-breadth criterion to the ticker-*eligible*
subset (SEC-listed equity issuers, cross-checked against `company_tickers.json`) — not the
full active/tracked universe, which by design includes non-ticker-bearing filer types. A
"100% of active companies have a ticker" criterion would be categorically wrong. See ticket
40's Answer for the full evidence (per-source population table, entity_type breakdown, code
citations). Ticket 40 marked resolved; unblocked (`Blocked by:` cleared) — ready to draft the
actual criteria list next.

## Answer

Grounded in the real schema (`EDGARTOOLS_GOLD.COMPANY` post-enrichment, `MDM_COMPANY_ENTITY`,
silver `sec_company_ticker`), ticket 27's ER-skill survey (F1 section), and ticket 40's full
reconciliation of the two prior open questions (ticker-population rate, `TICKER_REFERENCE`
bug). Every criterion below must pass; several were shaped specifically to avoid repeating the
two false alarms ticket 40 had to untangle — an adversarial pass against a naive version of
this checklist would have gated on "100% of active companies have a ticker" or trusted
`TICKER_REFERENCE` as populated, both of which are wrong.

1. **A documented, working read path must exist — this is the actual promotion blocker today.**
   Per the coverage matrix's own definition, "Covered" requires a *documented ER read path*, not
   just data existing somewhere in the warehouse. Today there is none: `TICKER_REFERENCE` (the
   table shaped and positioned to be that path) is 0 rows (ticket 40, export gated to the
   one-time `seed-universe` command); `MDM_COMPANY_ENTITY.ticker` is healthy data but is an MDM
   export target, not a documented ER-facing surface (`docs/subject-bundle-read.md` has zero
   ticker mentions). **This criterion fails until ticket 40's recommended fix ships**
   (`build_ticker_reference_table` rewired to read from silver `sec_company_ticker`, exported on
   `gold-refresh`) and the resulting table/read path is documented on the Subject Bundle or
   equivalent ER-facing contract.
   Acceptance: `SELECT COUNT(*) FROM EDGARTOOLS_GOLD.TICKER_REFERENCE` > 0 **and** a same-day
   `last_sync_run_id` appears in the most recent `gold-refresh` run's manifest (proves it's
   live-refreshed, not a one-time snapshot) **and** the read path is named in
   `docs/subject-bundle-read.md` or an equivalent documented contract.

2. **Ticker-eligible coverage — cross-checked against SEC's own ticker file, not the full
   tracked universe.** Per ticket 40: the tracked/active universe is 88.9% non-equity filer
   types (insiders, advisers, broker-dealers, trusts) that structurally have no ticker — a
   full-universe coverage bar is categorically wrong. The correct population is the
   ticker-*eligible* subset: active companies present in SEC's own
   `https://www.sec.gov/files/company_tickers.json`. Bar: **≥95%** of that eligible subset has a
   non-null ticker in the canonical source (a much higher bar than the coverage-promotion
   precedent's 50%, because unlike a brand-new Explore product, this data is proven
   already-healthy at ~99.5% match rate on the CIKs that are in both sets — ticket 40's own
   numbers: 2,576 SEC-listed of `active` CIKs, essentially all recoverable from silver
   `sec_company_ticker`'s 8,056-CIK near-exact match to SEC's 8,017).
   Acceptance:
   ```sql
   -- eligible = active CIKs present in a loaded snapshot of SEC's company_tickers.json
   SELECT COUNT(*) FILTER (WHERE tr.ticker IS NOT NULL) * 1.0 / COUNT(*) >= 0.95
   FROM eligible_ciks e
   LEFT JOIN EDGARTOOLS_GOLD.TICKER_REFERENCE tr ON tr.cik = e.cik
   ```

3. **No full-universe coverage criterion exists, and none should ever be added.** Explicit
   negative criterion, not just an omission: any future revision of this checklist that adds
   "X% of all active companies have a ticker" (unscoped to the eligible subset) is wrong on its
   face per ticket 40's evidence and must be rejected, not just questioned.

4. **Canonical-source agreement — no silent divergence.** `MDM_COMPANY_ENTITY.ticker` is a
   derived copy of silver `sec_company_ticker` (via `mdm/universe.py::bulk_upsert_universe`),
   not an independent source. Any row where both are populated but disagree indicates a sync
   bug, not a data-quality issue to route around.
   Acceptance: `SELECT COUNT(*) FROM MDM_COMPANY_ENTITY m JOIN <silver sec_company_ticker export
   or its Snowflake mirror> s ON m.cik = s.cik WHERE m.ticker IS NOT NULL AND s.ticker IS NOT
   NULL AND m.ticker <> s.ticker` = 0.

5. **Ticker uniqueness among currently-active companies — collision handling.** A ticker maps
   to at most one *currently active* company at a time (delisted companies' historical tickers
   reused by later IPOs must not create a live collision). Multi-class tickers (e.g. dual-class
   shares, same CIK with 2 tickers) are a legitimate exception and must not be flagged.
   Acceptance: `SELECT ticker, COUNT(DISTINCT cik) FROM TICKER_REFERENCE tr JOIN COMPANY c ON
   c.cik = tr.cik WHERE c.tracking_status = 'active' GROUP BY ticker HAVING COUNT(DISTINCT cik)
   > 1` returns zero rows.

6. **Format-verified provenance, not fabricated rows.** Every promoted ticker row's
   `last_sync_run_id` traces to a real `company_tickers`/`company_tickers_exchange` sync job
   (silver `sec_company_ticker.source_name` — ticket 40's finding). A row with no traceable
   source run, or a `source_name` outside that pair, is not promotion-eligible — same shape as
   `erdp-coverage-promotion` ticket 03's Yahoo-format-verification criterion, adapted to this
   product's actual provenance field.

7. **Company name presence alongside ticker.** Per ticket 27's F1 survey, every skill that
   needs identity wants ticker *and* company name together (thesis-tracker: "Name and ticker";
   idea-generation/sector-overview templates always pair them) — a ticker with a null or
   placeholder `entity_name`/`canonical_name` fails this criterion even if the ticker itself is
   valid.
   Acceptance: `SELECT COUNT(*) FROM TICKER_REFERENCE tr JOIN COMPANY c ON c.cik = tr.cik WHERE
   c.entity_name IS NULL OR TRIM(c.entity_name) = ''` = 0.

8. **Freshness — loose bound, not a same-day requirement.** Ticket 27 found no skill states a
   freshness requirement for identity data (tickers change rarely; contrast F18 Earnings
   calendar, where catalyst-calendar explicitly warns dates shift). Set a sanity bound, not a
   skill-derived one: canonical source's most recent sync completed within **30 days** of any
   promotion check — catching a pipeline going silently stale, not chasing same-day freshness no
   skill asked for.

9. **Join integrity to `COMPANY`.** 100% of `TICKER_REFERENCE` rows join to `COMPANY` on `cik`
   with no orphans (every ticker row resolves to a real, known company) — the inverse direction
   (criterion 2) already covers "every eligible company has a ticker."

**Explicitly not required for promotion** (per ticket 27, no ER skill needs it): ticker-change
history (every skill wants only the current mapping); CIK exposed anywhere in ER-facing output
(no skill ever references CIK by name — it is a platform-internal join key, not part of the ER
contract); exchange/listing-venue detail beyond what's needed for the join (no skill asks for
it); same-day freshness (no skill states this requirement).

**Known residual risk, not closable by any acceptance query:** criterion 1 (working read path)
is a hard gate on work that has not happened yet — this checklist describes the bar, it does
not itself fix `TICKER_REFERENCE`. Until ticket 40's recommended fix ships and is verified live,
Identity remains **not promotable to Covered**, regardless of how well criteria 2–9 score
against the currently-healthy-but-undocumented `MDM_COMPANY_ENTITY`/silver data. Also: the 27%
gap within `entity_type='operating'` CIKs not matching SEC's ticker file (ticket 40) is presumed
to be legitimately non-ticker filers (private debt issuers, foreign private issuers, pending
Form 15 deregistrations) — this was inferred from SIC/entity sampling, not individually
verified CIK-by-CIK, so criterion 2's 95% bar should be revisited if a future check finds that
gap is larger or different in composition than currently understood.
