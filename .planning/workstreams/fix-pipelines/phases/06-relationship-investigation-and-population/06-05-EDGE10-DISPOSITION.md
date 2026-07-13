# 06-05 EDGE-10 (AUDITED_BY) Disposition

**Plan:** 06-05 (Wave 3, fix-pipelines)
**Status:** COMPLETE. Task 1 (coordination gate) approved by operator ("approved"). Task 2
(root-cause) and Task 3 (disposition) both complete: EDGE-10 is disposed as a **source-coverage
exclusion** — the SEC `companyfacts` API this platform fetches from structurally cannot deliver
the `ix:nonNumeric`-tagged `AuditorFirmId`/`AuditorName`/`AuditorLocation` DEI facts, confirmed via
live SEC EDGAR evidence (see Task 2/3 below). AUDITED_BY graph edge count: 0 (documented
exclusion, not an undocumented zero state).

---

## Task 1: Coordination gate for any additional entity-facts fundamentals run

### 1. Is the entity-facts prerequisite already present in unified silver?

Source: `06-03-LOAD-COVERAGE-EVIDENCE.md`, Task 3 per-type coverage table (completed
2026-07-12, read-only query against the canonical dev silver
`s3://edgartools-dev-warehouse/warehouse/silver/sec/silver.duckdb`, 635 MiB,
last modified 2026-07-10T23:39Z):

| Signal | Value |
|---|---|
| `sec_financial_fact` rows (companyfacts entity-facts source) | **2,729,147** |
| `sec_financial_derived` rows (computed from the same entity-facts fetch) | **28,552** |
| `sec_accounting_flag.auditor_pcaob_id` rows (DEI-derived, EDGE-10's actual target) | **0** |

06-03's own classification for EDGE-10: **"ARTIFACT PRESENT, SILVER EMPTY"** — i.e. the
companyfacts entity-facts artifact for the loaded 150-CIK universe was fetched and successfully
parsed into `sec_financial_fact`/`sec_financial_derived` (2.7M + 28,552 rows prove the fetch and
the numeric-fact parsing path both ran and produced real rows), but the narrower DEI-auditor
subset of that same parse (`sec_accounting_flag.auditor_pcaob_id`, populated by
`parse_entity_facts` in `edgar_warehouse/parsers/financials.py` from the `dei` section of the
same companyfacts JSON) is at zero.

**Verdict: the entity-facts prerequisite IS present in the unified silver.duckdb.** This is not
the "entity-facts absent" branch the plan's Task 1 action anticipated (which would require a
fresh `bootstrap-fundamentals entity-facts` fetch run). Companyfacts data for this CIK universe
has already been fetched and parsed at least once (evidenced by the non-zero
`sec_financial_fact`/`sec_financial_derived` rows produced from that exact fetch).

### 2. Why no new fetch run is being requested right now

Two hypotheses remain open for *why* `sec_accounting_flag.auditor_pcaob_id` is 0 despite the
companyfacts fetch having succeeded, and neither one is decided by this checkpoint — that's
Task 2/3 root-cause work, done only after this gate clears:

1. **Parser/write-path gap** — something between `parse_entity_facts`'s DEI-derived
   `sec_accounting_flag` rows and `SilverDatabase.merge_accounting_flags` drops or fails to
   persist those rows even though the `dei` section of the fetched JSON contains
   `AuditorFirmId`/`AuditorName` facts.
2. **Genuine dei-absence for this specific 150-CIK universe** — `dei:AuditorFirmId` is a
   post-FY2021 HFCAA-driven DEI XBRL tag; if none of the 150 loaded CIKs' most recent annual
   filings in scope report it (e.g. small/foreign filers with delayed compliance, or the
   in-scope filings predate the requirement), zero accounting-flag rows would be the correct,
   non-buggy result for *this* universe, not a defect.

Both hypotheses are read against **already-fetched, already-parsed companyfacts data** that is
sitting in the unified silver.duckdb right now. Neither one requires re-fetching companyfacts
from SEC to investigate:
- Hypothesis 1 (parser/write-path gap) is fixed in code and verified by re-running the existing
  parser against the already-captured JSON (or by inspecting `merge_accounting_flags`/the DEI
  section directly) — no new SEC round-trip needed.
- Hypothesis 2 (genuine dei-absence) is falsified or confirmed by inspecting the same
  already-fetched JSON's `dei` section for the 150 CIKs — again no new fetch needed to check.
- Per DEC-009, re-running `bootstrap-fundamentals entity-facts` against the same CIKs would be a
  no-op fetch-wise in any case (idempotent skip of already-captured companyfacts), so it would
  not by itself produce new evidence about either hypothesis.

**Verdict: no new/additional entity-facts fetch run is needed as the immediate next step.**
The outcome is either (a) a parser/write-path fix applied to data already in unified silver
(Hypothesis 1, no fetch involved), or (b) a documented exclusion/finding that this universe's
DEI facts genuinely lack auditor tags (Hypothesis 2, also no fetch involved). Task 2/3 determine
which, without triggering a new `bootstrap-fundamentals entity-facts` run.

**Caveat (does not foreclose future coordination):** if Task 2/3's investigation instead shows
that the *fetched* companyfacts JSON for this 150-CIK universe never actually reached SEC's DEI
`AuditorFirmId` facts for a reason that would be fixed by re-fetching a differently-scoped or
larger universe (e.g. broadening beyond the 150-CIK D-02 bound, or the loaded universe skews to
filers whose annual filings predate FY2021), that would re-open the "is a fresh entity-facts run
needed" question and re-trigger this same coordination gate before any such run — this section
records the verdict for *now*, not a permanent closure of the coordination requirement.

### 3. Codex / `fundamental-factors-v2` coordination check (per CLAUDE.md / PROJECT.md standing caution)

Read `.planning/workstreams/fundamental-factors-v2/STATE.md` directly (not relying solely on the
orchestrator's framing) to confirm tombstone status independently:

- Frontmatter: `status: merged-into-fix-pipelines`, `merged_into: fix-pipelines`,
  `merged_date: "2026-07-11"`.
- `merged_note`: *"TOMBSTONE — consolidated into fix-pipelines on 2026-07-11 (Codex->Claude
  hand-off, user-authorized). Completed Phases 1-2 remain here as history. Outstanding Phase 3
  (cash-conversion-cycle) was grafted to fix-pipelines as unified Phase 10. Do NOT resume this
  workstream separately — see .planning/workstreams/fix-pipelines/ROADMAP.md."*
- Confirmed via `git branch -r | grep -i codex` — no remote branches matching `codex`. No
  `codex/fundamental-factors-v2` ref exists.
- `fix-pipelines/STATE.md` "Active Decisions" still carries the older standing caution text
  ("AUDITED_BY (EDGE-10) ... must coordinate with the active `fundamental-factors-v2` workstream
  (Codex)") — this predates the 2026-07-11 consolidation and is now superseded by the tombstone;
  not updated to reflect the merge as of this check (a documentation-lag observation, not a
  blocker).

**Conclusion: `fundamental-factors-v2` (Codex) is not an active, separate workstream.** It was
consolidated into `fix-pipelines` itself on 2026-07-11 (unified Phase 10, Codex→Claude
hand-off). There is no independent Codex runtime or branch that a fresh fundamentals run could
collide with — the "coordinate before running fundamentals in dev" constraint is now (per
06-03's own EDGE-10 coordination note, carried forward from 06-CONTEXT.md) an intra-workstream
sequencing concern, not a cross-runtime one. Combined with the Section 2 verdict (no new fetch
run is needed right now), this coordination check is moot for the immediate next step — but is
recorded here in case Task 2/3's investigation reopens the "is a fetch run needed" question per
the Section 2 caveat.

### 4. In-flight dev execution check (DEC-009 / no `--force`)

No entity-facts fetch run is planned as the immediate next step (Section 2), so there is no
run to check for overlap against right now. If Task 2/3 later determines a fresh
`bootstrap-fundamentals entity-facts` run is required after all (Section 2 caveat), that run
must (a) re-verify no `RUNNING` dev execution exists first (same check pattern 06-03 Task 1
used: `aws stepfunctions list-executions --status-filter RUNNING`) and (b) never pass `--force`
per DEC-009 (SEC data idempotency — already-captured companyfacts artifacts must be skipped by
default).

---

## Coordination outcome summary

| Check | Result |
|---|---|
| Entity-facts prerequisite present in unified silver | **YES** — `sec_financial_fact` (2,729,147 rows) and `sec_financial_derived` (28,552 rows) prove the companyfacts fetch+parse already ran for this universe |
| Is a fresh/additional entity-facts fetch run needed right now | **NO** — root-causing the `sec_accounting_flag.auditor_pcaob_id`=0 gap (parser/write-path vs. genuine dei-absence) does not require re-fetching; DEC-009 makes a same-universe re-fetch a no-op regardless |
| `fundamental-factors-v2` (Codex) active/in-flight, could a run overlap | **N/A / moot** — tombstoned into this same workstream 2026-07-11; no separate Codex branch or runtime exists (`git branch -r` confirms) |
| DEC-009 (no `--force`) honored | **N/A for now** (no run planned); recorded as a hard requirement if Section 2's caveat later triggers a run |

**This checkpoint does not self-approve.** Per the plan's `gate="blocking"` on Task 1, execution
stops here for explicit operator sign-off before Task 2 (parser/data root-cause work) proceeds.
See `<resume-signal>` in `06-05-PLAN.md`: type "approved" (no entity-facts fetch run needed;
proceed to Task 2's parser/data root-cause investigation against existing unified silver) or
describe a coordination blocker.

---

## Task 2: Root-cause of `sec_accounting_flag.auditor_pcaob_id` = 0 despite companyfacts entity-facts having run

**Status:** COMPLETE. Root cause confirmed via live SEC EDGAR fetches (this worktree has no live
dev AWS/Snowflake access — see the plan's realistic-scoping note — so this root-cause pass was
done entirely against real, currently-live SEC EDGAR data, not the dev `silver.duckdb`).

### Recap of the Task 1 finding this builds on

Task 1 established the entity-facts *prerequisite* is present: `sec_financial_fact` (2,729,147
rows) and `sec_financial_derived` (28,552 rows) prove the `companyfacts` fetch for this 150-CIK
universe already ran and successfully parsed numeric XBRL facts. That is a different claim from
"the auditor DEI facts are obtainable" — Task 2 shows those are two separate fact populations
inside the same SEC API response, and only one of them is exposed by the endpoint this platform
calls. No new fetch was triggered for Task 2 (consistent with Task 1's Section 2 verdict);
everything below is live read-only evidence gathering against the public, unauthenticated SEC
EDGAR API — `data.sec.gov` and `www.sec.gov` — to inspect the `dei` section shape and cross-check
it against an actual filing's inline XBRL.

### Code path read first (per `<read_first>`)

- `edgar_warehouse/application/workflows/fundamentals_ingest.py:run_bootstrap_entity_facts` —
  calls `build_companyfacts_url(cik)` → `download_sec_bytes` → `parse_entity_facts(cik,
  facts_json)` → `db.merge_accounting_flags(parsed["sec_accounting_flag"], ...)`. The write path
  (`merge_accounting_flags`) only ever receives whatever `parse_entity_facts` extracted — it does
  not independently touch SEC. **No bug found in this call chain.**
- `edgar_warehouse/parsers/financials.py:parse_entity_facts` — for each concept in
  `_DEI_AUDITOR_CONCEPTS` (`AuditorFirmId`, `AuditorName`, `AuditorLocation`,
  `IcfrAuditorAttestationFlag`), it reads `dei.get(dei_concept, {}).get("units", {})` and iterates
  facts inside. If `dei_concept` is absent from the `dei` dict entirely, the inner loop simply
  never executes for that concept — `accn_dei` stays empty and `accounting_rows = []`. **This
  matches exactly what live SEC data shows below: the code is dormant-correct, not buggy — it
  would parse these facts correctly if the API ever delivered them in this shape, but the API
  itself never populates `dei["AuditorFirmId"]` etc. at all.**

### Live SEC EDGAR evidence (root cause)

**1. The aggregate `companyfacts` API's `dei` section never contains the auditor concepts, for
any company tested.** Fetched real, current `/api/xbrl/companyfacts/CIK{cik}.json` responses
(the exact same endpoint `build_companyfacts_url`/`run_bootstrap_entity_facts` calls) for three
large, unrelated filers:

| CIK | Company | `facts.dei` keys present |
|---|---|---|
| 0000320193 | Apple | `EntityCommonStockSharesOutstanding`, `EntityPublicFloat` |
| 0000789019 | Microsoft | `EntityCommonStockSharesOutstanding`, `EntityListingParValuePerShare`, `EntityPublicFloat` |
| 0001045810 | NVIDIA | `EntityCommonStockSharesOutstanding`, `EntityPublicFloat` |

None of the three companyfacts responses contain `AuditorFirmId`, `AuditorName`, or
`AuditorLocation` anywhere in the JSON (`grep -ci auditor` on each raw response = 0; also
confirmed via a recursive key search, not just a top-level key check).

**2. The underlying 10-K filings DO tag these facts — the data exists, it just never reaches the
companyfacts endpoint.** Apple's FY2025 10-K (accession `0000320193-25-000079`, filed 2025-10-31)
has a dedicated "Auditor Information" XBRL viewer sheet (`R2.htm`, per `FilingSummary.xml`)
showing:

```
Auditor Name:     Ernst & Young LLP     (dei:AuditorName)
Auditor Location: San Jose, California  (dei:AuditorLocation)
Auditor Firm ID:  42                    (dei:AuditorFirmId)
```

Confirmed directly in the raw inline-XBRL filing document
(`aapl-20250927.htm`): `<ix:nonNumeric contextRef="c-1" name="dei:AuditorFirmId" id="f-1130">42`.

**3. The exclusion mechanism is fact-*type*-based, not auditor-specific — confirmed with a
control.** `dei:AuditorFirmId`/`AuditorName`/`AuditorLocation` are all tagged with
`<ix:nonNumeric>` (text/token-typed XBRL facts — no unit, no numeric value), in contrast to
`EntityCommonStockSharesOutstanding`/`EntityPublicFloat` (`<ix:nonFraction>`, numeric with units —
these DO show up in companyfacts). To rule out "auditor tags specifically are excluded" versus "
all nonNumeric dei facts are excluded," the same Apple filing's inline XBRL also tags
`dei:EntityRegistrantName` (also `ix:nonNumeric`, and a universally-present cover-page fact on
literally every 10-K) — yet `EntityRegistrantName` is likewise **absent** from Apple's
companyfacts `dei` section (only the two numeric facts listed above are present). This control
confirms the gap is systemic to `ix:nonNumeric`-tagged `dei` facts, not something specific to
auditor concepts — the `companyfacts` aggregation endpoint only surfaces numeric
(`ix:nonFraction`, unit-bearing) facts.

**4. Cross-checked against SEC's per-concept API too, not just the aggregate endpoint.**
`https://data.sec.gov/api/xbrl/companyconcept/CIK0000320193/dei/AuditorFirmId.json` and the same
path for Microsoft both return HTTP 404 — the per-concept endpoint (which draws from the same
underlying numeric-facts store as `companyfacts`) has no record of this concept for either
company either. This is the same underlying data source as `companyfacts`, so the 404 is
consistent with, not independent confirmation beyond, finding #1 — but it does rule out
"maybe it's aggregated under a different endpoint path than the one this code calls."

### Root cause (5-whys)

1. **Symptom:** `sec_accounting_flag.auditor_pcaob_id` = 0 for all 150 loaded CIKs despite a
   confirmed-successful `companyfacts` entity-facts fetch+parse (Task 1).
2. **Why:** `parse_entity_facts`'s DEI-auditor branch (`_DEI_AUDITOR_CONCEPTS` loop) never finds
   `AuditorFirmId`/`AuditorName`/`AuditorLocation` keys under `facts_json["facts"]["dei"]`, so
   `accn_dei` stays empty for every CIK, every run.
3. **Why:** The SEC `companyfacts` API response's `dei` section genuinely does not contain those
   keys — confirmed empirically on 3 unrelated large-cap filers (Apple, Microsoft, NVIDIA), not
   just the loaded universe.
4. **Why:** Those three DEI concepts are tagged in the filings as `ix:nonNumeric` (text-typed)
   XBRL facts. The `companyfacts`/`companyconcept` APIs only aggregate `ix:nonFraction`
   (numeric, unit-bearing) facts into their JSON structure — confirmed by the `EntityRegistrantName`
   control (also `ix:nonNumeric`, also absent from companyfacts, despite being present in every
   filing and having zero relationship to auditor data).
5. **Root cause:** The platform's `bootstrap-fundamentals entity-facts` fetch path is built
   entirely on the `companyfacts` aggregate API, which structurally cannot deliver `ix:nonNumeric`
   DEI facts — regardless of universe size, CIK selection, run count, or `--force`. The auditor
   PCAOB-ID/name/location data genuinely exists in every 10-K's inline XBRL (confirmed directly on
   Apple's FY2025 filing) but is not reachable through the SEC data source this parser reads from.
   This is **not** a bug in `parse_entity_facts`/`merge_accounting_flags` (both are dormant-correct
   for a shape that never arrives) and **not** genuine post-FY2021 DEI-absence in the filings
   (confirmed present). It is a genuine, structural gap between the SEC endpoint this platform
   fetches from and the SEC endpoint (or per-filing inline-XBRL parse) that would actually carry
   this data.

**This finding is scoped to the `companyfacts`-API extraction path this codebase currently uses —
not a claim that PCAOB auditor data is unobtainable from SEC EDGAR in general.** The data is
confirmed present in every 10-K's own inline XBRL (`R2.htm`-equivalent "Auditor Information"
sheet). Obtaining it would require a *different* ingestion path — parsing each 10-K accession's
own inline XBRL cover-page/audit-report facts (architecturally similar to the existing
`per-filing` bootstrap-fundamentals mode, which already parses bronze-captured filing documents
directly rather than calling the CIK-level `companyfacts` aggregate) — which is a new ingestion
surface, not a fix to the existing entity-facts fetch or parser. Building that is out of this
plan's scope (Rule 4 — architectural change) and is not attempted here.

**Generalization caveat:** the "companyfacts `dei` section never carries these facts" result is
confirmed empirically on 3 unrelated large-cap filers plus the `EntityRegistrantName` control (4
independent data points showing the same fact-type-based exclusion), and is consistent with how
SEC's XBRL frames/companyfacts aggregation is documented to work (numeric facts table only). It
is *inferred*, not individually re-verified, for all 150 CIKs in the loaded universe — the
`sec_accounting_flag.auditor_pcaob_id = 0` count for that universe comes from 06-03's Task 1
finding above, not from re-checking each of the 150 CIKs' own companyfacts responses in this
worktree.

### Entity-facts prerequisite recorded (per plan's acceptance criteria)

- `sec_accounting_flag.auditor_pcaob_id` has **zero rows**, and it got there via: the companyfacts
  entity-facts fetch **did run** (Task 1: proven by nonzero `sec_financial_fact`/
  `sec_financial_derived`), but the auditor-specific DEI facts it needs were **never present in
  that API response to begin with** — confirmed via live SEC data (this section), not a parser or
  write-path defect.
- Fundamental-factors-v2 (Codex) coordination record: see Task 1 Section 3 — tombstoned into this
  workstream 2026-07-11, no separate runtime/branch exists, moot for this investigation since no
  new fetch was triggered.
- DEC-009 (no `--force`): honored — no entity-facts fetch run was triggered at all in Task 2 (all
  evidence gathered via read-only SEC EDGAR calls against public endpoints, no repo commands run
  against dev infrastructure).

---

## Task 3: AUDITED_BY disposition — source-coverage exclusion

**Status:** COMPLETE — **source-coverage exclusion** (not populated). No new deriver code was
written; `_derive_audited_by` (`edgar_warehouse/mdm/pipeline.py:1214-1330`) was read to confirm it
is correct as-is and requires no changes.

### Why this is an exclusion, not a populate-and-verify

Per the plan's Task 3 branching: "If entity-facts data could not be landed at all... write a
source-coverage exclusion naming the SEC companyfacts entity-facts dependency and the reason it
was unobtainable this run." Task 2 established exactly that condition for the auditor-specific
facts: the `companyfacts` API this platform's `bootstrap-fundamentals entity-facts` command calls
structurally cannot deliver `dei:AuditorFirmId`/`AuditorName`/`AuditorLocation` (confirmed via
live SEC data — see Task 2). `_derive_audited_by` reads:

```sql
SELECT cik, accession_number, fiscal_year, period_end,
       auditor_pcaob_id, auditor_name, icfr_attestation
FROM sec_accounting_flag
WHERE auditor_name IS NOT NULL OR auditor_pcaob_id IS NOT NULL
```

Since `sec_accounting_flag.auditor_pcaob_id`/`auditor_name` will be NULL for every row regardless
of how many times `bootstrap-fundamentals entity-facts` is re-run (Task 2's root cause is
structural, not transient), running the AUDITED_BY derivation now would deterministically produce
**0 rows selected, 0 inserted** — not because of a graph-sync defect, but because the source table
that feeds it has no qualifying rows and cannot get any via the current fetch path. Running the
derivation step in dev right now would not produce new evidence beyond what Task 2 already
established from the source data directly; it is not run here.

### Source-coverage exclusion (formal statement)

**AUDITED_BY (EDGE-10) is excluded from this population run.** Dependency:
SEC `companyfacts` (XBRL entity-facts) API, specifically the `dei` section's
`AuditorFirmId`/`AuditorName`/`AuditorLocation` concepts.

**Reason unobtainable this run:** the `companyfacts` API endpoint
(`data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json`) that `bootstrap-fundamentals entity-facts`
fetches from does not include `ix:nonNumeric`-tagged DEI facts in its response — confirmed via live
fetches against 3 filers plus a same-filing control (`EntityRegistrantName`, also absent). The
auditor PCAOB ID/name/location data is real and present in every 10-K's own inline XBRL (verified
directly on Apple's FY2025 10-K, R2.htm "Auditor Information" sheet: PCAOB ID 42, Ernst & Young
LLP, San Jose CA) — but is not reachable through the SEC endpoint this platform's entity-facts
fetch path uses. No amount of re-running `bootstrap-fundamentals entity-facts` (with or without
`--force`, against this 150-CIK universe or a larger one) will populate
`sec_accounting_flag.auditor_pcaob_id`, because the source API this platform calls does not carry
that data for any company.

**Path to resolving EDGE-10 in a future plan (not attempted here — architectural, Rule 4):** add a
new per-filing ingestion path that parses each 10-K accession's own inline XBRL cover-page/audit
disclosure facts directly (bronze-captured filing document → `dei:AuditorFirmId`/`AuditorName`/
`AuditorLocation` extraction), architecturally similar to the existing `per-filing`
bootstrap-fundamentals mode (which already parses bronze-captured 8-K/DEF 14A documents directly
rather than calling a CIK-level aggregate API). This is a new parser + a new bronze-artifact
dependency (each 10-K's own htm/XBRL document, not the `companyfacts` JSON), not a fix to the
existing `parse_entity_facts`/`_derive_audited_by` code, which is confirmed correct for the data
shape it is given.

**Outcome:** AUDITED_BY graph edge count: **0** (no derivation run — deterministically 0 rows
would be selected from `sec_accounting_flag` given Task 2's finding, so running `mdm
derive-relationships --relationship-type AUDITED_BY` / `mdm sync-graph` now would not produce new
evidence). EDGE-10 disposed as a documented **source-coverage exclusion**, not an undocumented
zero state (T-06-07 mitigated).

---

### Observation (out of scope for this checkpoint, flagged for the operator)

`fix-pipelines/REQUIREMENTS.md`'s traceability table (lines ~100-102) already marks EDGE-09,
EDGE-10, and EDGE-11 as **"Complete"** for Phase 6, and the requirement bullets themselves
(lines 43-45) are checked `[x]` — despite `fix-pipelines/STATE.md` recording that Phase 6 is
still executing (plan 3 of 6, 06-04 not yet started at the time this doc was written, 06-05 not
yet approved past Task 1). This looks like a premature status update, most likely introduced
during the 2026-07-11 consolidation commit (`618049e`) rather than anything from this plan's
execution. Not corrected here — REQUIREMENTS.md is a shared orchestrator-owned artifact and this
worktree agent is stopping at a checkpoint, not completing the plan.
