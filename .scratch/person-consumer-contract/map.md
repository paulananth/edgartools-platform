# Person Consumer Contract

Label: `wayfinder:map`

## Destination

A decision-complete **Person consumer specification** — every SEC source that
yields a natural person, what may bind one to a Person Identity, what
projects, what relationships publish, privacy and retention, migration from
legacy Person IDs, tests and release gates — handed to Codex/Grok as the
contract their Clean MDM Person integration must satisfy. **Complete Person
scope, not a slice** (operator, 2026-09-19). Planning only: no code, no
migration, no edit to any Clean MDM file. Written at
`docs/specs/person/consumer.md` when this map is done.

**Destination reached, 2026-09-20.** Every decision ticket is resolved and
the spec is written: [`docs/specs/person/consumer.md`](../../docs/specs/person/consumer.md),
handed over in
[`.scratch/handover/2026-09-20-claude-to-codex-person-consumer.md`](../handover/2026-09-20-claude-to-codex-person-consumer.md).
What remains on this map is not decisions:
[ticket 21](issues/21-extend-tier-b-labelling-to-97-5.md) is resolved — Tier B
is qualified for 8-K — leaving code-owner tasks only:
[10](issues/10-fix-proxy-executive-name-parser-leak.md) (proxy name parser —
**fixed 2026-09-20**, 48.6% → 100% plausible names on real filings; open until
a full local re-parse of bronze is measured — the production re-export is
deferred until all code is written and tested locally),
[22](issues/22-decommission-legacy-person-code-and-tests.md) (decommission
legacy Person code, gated on the Clean MDM consumer being live).

**Documentation review passed, 2026-09-20.** Every citation and headline
figure in the spec re-verified against the repository and the research files;
four defects found and fixed, all overstatements rather than wrong decisions —
a moved line number in `company-completion.md`, gold's owner key described as
a hash when it is a concatenated natural key, the 8-K and DEF 14A name-quality
figures taken from research 01's looser measure instead of research 17's
person-shape filter (53.2% and 41.3%, not 97.7% and "58.7% role text"), and a
distinct-CIK count borrowed from a different study. Detail on
[ticket 08](issues/08-write-person-consumer-spec.md).

## Notes

- **Why now**: Codex's `docs/specs/clean-mdm/company-completion.md` line 80
  forbids starting Person *integration* until the local Company gate
  passes. That is an implementation ordering on their side. Planning the
  Person contract in parallel is the same move that produced the Company
  contract (`.scratch/gleif-company-augmentation/spec.md`): Claude writes the
  contract, Codex builds against it, nothing collides.
- **Target**: Clean MDM only. Legacy MDM (`edgar_warehouse/mdm/resolvers/person.py`,
  `pipeline.py`'s `IS_INSIDER`/`EMPLOYED_BY`/`IS_PERSON_OF` derivations) is
  being decommissioned (operator directive, 2026-09-19) and is cited here
  only as evidence of current behavior. Person is already one of Clean
  MDM's two first identities (`mdm_v2.identity.kind = 'person'`,
  `docs/specs/clean-mdm/domain-model.md` line 25), and their
  `pipeline-inventory.md` rows 23/26/29 already sketch target designs for
  each Person source — this map's contract cites those, never redefines
  them, exactly as the Company contract does.
- **Not enrichment**: Person is the SEC multi-source Person domain, not GLEIF
  enrichment. The MDM Enrichment Program explicitly excludes human-person
  enrichment from LEI evidence; its workstream 08 (sole-proprietor boundary)
  is a narrow GLEIF privacy decision and stays there.
- **Source inventory, verified against `edgar_warehouse/silver_schema.py`
  2026-09-19** (complete: no other silver table carries a natural person):

  | Silver table | Filing | Identifier | Legacy relationship |
  | --- | --- | --- | --- |
  | `sec_ownership_reporting_owner` (+ `sec_ownership_*_txn`) | Form 3/4/5 | `owner_cik` (SEC CIK of the individual), name, director/officer/10%/other flags, title | `IS_INSIDER`, `HOLDS` |
  | `sec_executive_record` | DEF 14A | name only (`exec_name`, role, compensation by fiscal year) | `EMPLOYED_BY` |
  | `sec_employment_event` | 8-K Item 5.02 | name only (`person_name`, role, event type, effective date) | `EMPLOYED_BY` |
  | `sec_adv_filing` | Form ADV | CRD number, where the registrant is an individual | `IS_PERSON_OF` (Clean MDM: same-ID Adviser profile membership instead) |

  Two consequences drive the tickets: reporting owners include *entities*
  (10% owners are often funds or companies), and two of four sources are
  **name-only** under a repo-wide rule that name similarity never binds.
- Legacy matching for reference: `CIKExactMatcher` → `FuzzyNameMatcher`
  with `issuer_cik` context → optional Splink (`resolvers/person.py`
  lines 40–57). Clean MDM's Q11/Q16 disables unqualified automatic rules;
  this map does not reopen that.
- Legacy Person IDs do not carry into `mdm_v2`: "Legacy IDs become an
  explicitly verified, versioned crosswalk" (`domain-model.md` line 87).
  Silver's back-propagated `mdm_entity_id` columns are legacy IDs.
- Skills: `/grilling` (operator preference: **one question at a time**),
  `/domain-modeling`. `CONTEXT.md` already defines **Person Identity**
  ("distinct from a Company and shared with an applicable individual
  Adviser profile"; avoid: employer identity, role as identity, same name
  as proof of sameness).

## Decisions so far

- [Measure how far name-only Person sources can be bound deterministically](issues/01-measure-name-only-source-overlap.md)
  — measured from S3 export snapshots (prod Snowflake is suspended:
  "free trial has ended", and will not be restored — the reporting-owner
  half now comes from the code traces in tickets 11–14). Proxy `exec_name` is 47% role text — a parser defect
  (ticket 10), so proxy cannot bind until fixed. 8-K names are 97.7% clean;
  `(issuer CIK, normalized name)` is the only deterministic key; 398 of
  10,042 names appear under more than one issuer, so a name never binds
  alone or across issuers. Findings:
  [research/01](research/01-name-only-source-overlap.md).
- [Trace the Form 3/4/5 reporting-owner Person pipeline from code](issues/11-trace-ownership-person-pipeline.md)
  — `owner_cik` is the only identifier, stored nullable/non-unique; the
  legacy fuzzy "issuer context" is inoperative and REVIEW still binds;
  classification is only "CIK ∈ company CIKs ⇒ not a person"; every
  transaction is hard-attached to owner 1; silver's `mdm_entity_id` is
  not a stable person key. [research/11](research/11-ownership-person-pipeline.md).
- [Trace the DEF 14A executive-record Person pipeline from code](issues/12-trace-proxy-executive-person-pipeline.md)
  — the 47% role-text names are an **edgartools** (PyPI) extractor defect,
  verified; no person identifier; legacy bypasses the resolver with a
  global exact-name lookup and per-issuer stubs that are never retired.
  [research/12](research/12-proxy-executive-person-pipeline.md).
- [Trace the 8-K Item 5.02 employment-event Person pipeline from code](issues/13-trace-8k-employment-event-person-pipeline.md)
  — no identifier; `(issuer CIK, name)` is the only context and is exactly
  legacy's stub key; `EMPLOYED_BY` from 8-K has never been graph-populated.
  [research/13](research/13-8k-employment-event-person-pipeline.md).
- [Trace the Form ADV individual-registrant Person pipeline from code](issues/14-trace-adv-individual-person-pipeline.md)
  — CRD keys an Adviser, never a Person; no code tells an individual
  registrant from a firm; `IS_PERSON_OF` has no reader anywhere; Schedule
  A/B and Part 2B persons are not parsed on any path.
  [research/14](research/14-adv-individual-person-pipeline.md).
- [Research CRD versus CIK: what each identifies, and whether they can be merged into one Person key](issues/15-research-crd-vs-cik-identifier-semantics.md)
  — CIK is an SEC filer account (people included); CRD is a FINRA/IARD
  registration record, firm and individual numbers distinct; no
  individual-level crosswalk exists; IARD and CRD share one number space;
  the bulk archive is firms-only for IARs **but already contains
  `IA_Schedule_A_B`** (11,126 individual owner rows with an unpublished
  `OwnerID`) and `IA_1D3_CIK`, both unread today. Two typed identifiers,
  not one mergeable key. [research/15](research/15-crd-vs-cik-identifier-semantics.md).
- [Research what ADV Schedule A/B `OwnerID` is](issues/16-research-schedule-ab-ownerid-meaning.md)
  — it is a CRD-system individual record id (IARD FAQ: "Create Individual
  … to assign the individual a CRD number"); 99.6% present, disjoint from
  firm CRDs, 5,322/5,322 stable month to month, 110/110 name-exact where
  IAPD resolves it. **Not** unique per natural person (duplicates exist by
  the issuer's own admission; two both-resolving same-person pairs found),
  and only ~54% corroborate publicly. [research/16](research/16-schedule-ab-ownerid-meaning.md).

- [Decide which evidence may bind a source record to a Person Identity](issues/02-decide-what-binds-a-person.md)
  — **one Person, one MDM id; every source id is a cross-reference.**
  `owner_cik` and Schedule A/B `OwnerID` bind deterministically (one id →
  exactly one Person; duplicate CRD records collapse onto one Person);
  no Person is created without a match attempt; tiers A (shared id, auto)
  / B (compound context key, auto at a measured ≥ **99%** precision — an
  operator amendment to Clean MDM's 99.9%, proposed to Codex) / C (fuzzy,
  Steward) / D (reject). Reading `IA_Schedule_A_B` is in scope.
  **§4's Tier B row is superseded by [ticket 20](issues/20-redecide-tier-b-after-calibration.md)**
  after the calibration; everything else stands.
- [Measure which reporting-owner classification rule reaches 99% precision](issues/18-measure-reporting-owner-classification-precision.md)
  — from bronze (5,743 owner rows, 4,831 CIKs, all with a captured
  `submissions.json`; 1,220 labeled): SEC `entityType='other'` is 71%
  person and `10%-only` is 72% entity, so neither may decide; "no legal-form
  token + structurally-empty SEC profile + person-shaped name" is 841/841
  for person; unambiguous-token entity is 518/520 with both misses being
  persons whose surname is a token. Flags add nothing. edgartools already
  fetches every owner's submissions live at parse time and computes an
  `is_company` the repo discards. [research/18](research/18-reporting-owner-classification-precision.md).
- [Decide how Form 3/4/5 reporting owners are classified as Person vs entity](issues/03-decide-reporting-owner-classification.md)
  — **rule C-J**, per owner CIK: no `submissions.json` → deferred; SEC
  `operating`/`investment` → company (bind by CIK); unambiguous legal-form
  token → entity of undetermined kind (terminal for Person, retained, no
  review) unless the single-token surname guard defers it; token-free +
  structurally empty + person-shaped → **person, automatic**; else Steward
  (~1.1% of owners, mostly persons SEC tagged with a state/FYE). Flags,
  `other`, and deputization text are evidence, never deciders; category,
  legal form, and kind recorded separately in `assertion.body` with rule
  id/version; kind correction is review + rebuild, never merge. Automatic
  entity decisions gated on re-measuring the post-hoc guards in production.
- [Decide the projected Person field set, privacy classification, and retention](issues/04-decide-person-fields-and-privacy.md)
  — the projection carries `legal_name` (survived by source rank),
  `display_name` (derived reorder rule), `name_variants[]`, the
  cross-reference identifiers, kind evidence, `profiles[]` (adviser by
  reference only), `last_observed`, **and a `roles[]` summary** — the
  operator chose read speed over an invariant-only identity, with three
  guards: same assertions and rule version as the relationship edges, same
  batch, and no matching rule may read it. Each role row carries
  `start_date`/`end_date` (null = no end known), `date_basis` ∈ {stated,
  observed} and `last_observed`, so "still serving" is never confused with
  "stopped filing". Compensation is retained, never projected; reporting-owner
  addresses are not captured at all (two booleans only). Privacy:
  public-record class, no redaction, no new role, four structural gates
  plus a Steward takedown path. Retention: permanent, no timer.
- [Calibrate the Person Tier B compound context key on a held-out sample](issues/17-calibrate-person-tier-b-context-key.md)
  — 921 labelled pairs, offline (ADV Schedule A/B March+August, 8-K and
  DEF 14A export snapshots, bronze Form 3/4/5), IAPD only to settle
  labels. **Tier B's stated home and its measured home are opposite.** On
  id-bearing sources Tier A binds first, so Tier B sees only the residual
  (same firm, same name, *different* ids): ADV 1 same / 27 different
  (precision 0.018), Form 3/4/5 residual empty. On the name-only sources
  it was written for it works: pooled 8-K + DEF 14A at the middle-initial
  variant, 269/269, **LCB95 0.99033 — clears 99%**, LCB97.5 0.98632 —
  does not (104 more labellable pairs exist). Homonyms are the failure
  mode (35 ADV pairs are separately registered individuals; father/son
  separated only by `JR`/`III`); reused ids do not exist (all 84 splits
  are one person under a name variant — pure recall cost); transitive
  bridges cannot exist under an equality key, but the looser Tier C
  comparator produces 48 chains of which 42 are false. Findings:
  [research/17](research/17-tier-b-context-key-calibration.md); the four
  consequent decisions: [ticket 20](issues/20-redecide-tier-b-after-calibration.md).
- [Re-decide Tier B now that it has been measured](issues/20-redecide-tier-b-after-calibration.md)
  — replaces ticket 02 §4's Tier B row. **Identifiers veto, everywhere**:
  two records carrying different values in the same namespace are vetoed
  and counted as `distinct_identified`, never auto-merged and never
  queued one at a time — stated in the Identifier Contract as a reason,
  not as a source list, so Tier B fires only where no identifier exists
  (8-K now, DEF 14A after ticket 10). **The bar becomes ≥ 99% at a
  one-sided 97.5% Wilson bound**, not 95%, so the Person amendment to
  Codex ships one bar; Tier B does **not** activate on today's numbers
  and 8-K stays Tier C until [ticket 21](issues/21-extend-tier-b-labelling-to-97-5.md)
  measures n ≥ 381. **The key** is same MDM-resolved issuer/firm identity
  + surname, given name and middle initial + **no generational-suffix
  conflict** (a hard veto, not a normalization step); role and flags are
  evidence, never key. DEF 14A is measured but not counted while 58.7% of
  its names are role text.
- [Decide how legacy Person IDs and silver back-propagated IDs map to mdm_v2](issues/06-decide-legacy-person-id-crosswalk.md)
  — **no crosswalk; legacy Person IDs are dropped, not mapped.** The
  operator asked why they are needed at all, and the holders answer it:
  legacy MDM Postgres is being decommissioned, silver's `mdm_entity_id`
  and the graph's person nodes live only in a Snowflake that will not be
  restored, the API is undeployed, and **gold never used them** (owners
  are keyed on a `cik:`/`name:` hash, `ownership_holdings.sql:63-67`).
  The ids are not worth carrying either: legacy's fuzzy context check can
  never pass, so `REVIEW` bound anything ≥ 0.80 Jaro-Winkler with no
  human gate. What does carry is human judgment — resolved
  `mdm_match_review` rows and merge tombstones, harvested as **source
  assertions** to be re-adjudicated, if that store is still reachable.
  Silver's column is frozen as legacy, never read or rewritten.
  Decommissioning the legacy Person code, its 15 test files and the dead
  columns: [ticket 22](issues/22-decommission-legacy-person-code-and-tests.md),
  gated on the Clean MDM Person consumer being live.
- [Decide Person processing cadence and the initial backfill scope](issues/07-decide-cadence-and-backfill.md)
  — three jobs, mirroring Company: **daily** on the issuers
  `daily_incremental` touched (never rematches the universe), **weekly**
  backstop over deferred records and Tier C candidates, **monthly** full
  reconciliation keyed to the ADV archive's release — the **only job that
  may close an interval by absence**, because two of ticket 05's three
  closers need a complete later filing set. Backfill is bounded by
  **evidence class**: wave 1 every Tier A bind plus rule C-J's person arm
  (deterministic, no review queue); wave 2 C-J's entity arm after its
  guards are re-measured; wave 3 8-K after ticket 21. **Replay re-enters
  at the pre-merge candidate stage** (operator), not at re-projection —
  only that corrects a wrong *binding* — which makes the pre-merge
  candidate table a requirement, not a proposal; a digest change is a
  bounded rebuild over the identities the changed rules reach.
  **Ids survive replay**: same id when the decision is unchanged, a split
  keeps the id holding the surviving authoritative identifier, a merge
  retires the loser with `superseded_by`, nothing is deleted and retired
  ids stay resolvable forever.
- [Decide which Person relationships publish and their semantics](issues/05-decide-person-relationships.md)
  — **a relationship is one mastered fact that every form contributes
  dated evidence to, not one edge per form** (operator requirement). Two
  types publish: `EMPLOYED_BY` (director/officer/employee) and `CONTROLS`
  (ten-percent owner, ADV owner with band, control person) — split by
  meaning, never by form. Key = (Person, Company, capacity); title is a
  dated property, not part of the key; each edge holds a **list of dated
  intervals**, so a departure and a re-appointment are never one span.
  Intervals close on a stated 8-K departure, on a later Form 3/4/5 that
  omits a previously-carried capacity flag, or on absence from a later ADV
  Schedule A/B roster — never on silence. Conflicts resolve stated-over-
  observed on **event dates**, so reporting lag is not a conflict and an
  announced departure is never silently reopened. Holdings (needs a
  Security identity **and** the `owner_index` parser fix) and
  `MANAGES_FUND` (needs Fund Structure) are **deferred records** that
  publish from history when their endpoint is accepted; `IS_PERSON_OF` is
  gone; `IS_INSIDER` survives as a view, not a mastered edge.

- [Extend the 8-K Tier B labelling to the 97.5% sample size](issues/21-extend-tier-b-labelling-to-97-5.md)
  — **Tier B is qualified for 8-K Item 5.02**, and for nothing else. The
  census of the population research 17 sampled (938 candidate pairs, 661
  matching ticket 20's fixed key): 658 `same`, **0 different**, 1 unknown, 2
  not person names. On n = 659, LCB97.5 is **0.99420** optimistic and
  **0.99146** conservative — both clear 99%, on n well past the 381 required.
  Cost: recall 0.7045 (a ~30% coverage loss to middle-name asymmetry) and
  15.26 reviews per 1,000 eligible records. **Power, not n, now binds**: every
  one of the 657 new pairs is `same`, and the only surviving route to a
  non-`same` label fires on 1 of 721 rows, so more labelling moves the bound
  rather than what can be detected. Confirms ticket 20's suffix veto against
  Form 3/4/5's 11 same-issuer homonym CIK pairs: plain `mi` merges 7, the veto
  prevents 6, the fixed key merges 1 — and that one is a multi-word-surname
  parse defect, not a key defect. Three normalizer repairs ship with
  activation: [ticket 25](issues/25-fix-person-name-normalizer-defects.md).
  Findings: [research/21](research/21-tier-b-8k-extended-labelling.md).

- [Add fiscal_year to the sec_executive_record collapse and gold grain](issues/23-fix-executive-record-collapse-key.md)
  — the silver collapse key and gold `fact_key` now carry `fiscal_year`,
  mirroring the landing key, so a three-year Summary Compensation Table
  yields three rows per executive (DuckDB replay: old key 1 of 3, new key 3
  of 3; three dbt unit tests). Gold's derived columns are now computed
  **within one filing** — a fiscal year is reported by three consecutive
  proxies, so the old `(cik, exec_name)` windows tied on year with no
  tiebreaker; one gold unit test covers the overlap. Zero retirement rows to
  re-key, by construction — the retirement table's only two writers target
  `sec_company_ticker` and `sec_filing_text`. Deploy needs `--full-refresh`
  on both tables, silver first; the re-export sequence is on ticket 10.

- [Give per-filing fundamentals a force/reprocess path](issues/24-reprocess-already-marked-fundamentals.md)
  — `bootstrap-fundamentals --force` now re-parses already-marked
  accessions for per-filing **and** 13F (one shared
  `_drop_already_processed` helper replacing two copied blocks), so ticket
  10's `PARSER_VERSION="2"` is reachable. Skip-by-default unchanged.
  Version-awareness on the marker table weighed and declined: a landing-zone
  schema migration for a table with no live migration path. 128
  fundamentals tests pass, 3 new.

- [Capture the reporting-owner evidence the Person contract needs, from bronze](issues/19-capture-ownership-parser-evidence.md)
  — the ownership parser reads the XML directly and classifies from bronze
  `submissions.json`, so a Form 3/4/5 parse makes **zero SEC requests**
  (edgartools fetched every owner live). Owner rows keep `owner_name_raw`,
  `other_text`, filing footnotes/remarks, two address booleans and rule
  C-J's structural fields with the snapshot's SHA-256; rule C-J from parser
  columns alone reproduces **841/841, 353/353, 26 deferred**. **Item 4
  restated**: the SEC schema gives a transaction no owner, so there is no
  real `owner_index` — transactions carry `reporting_owner_count`, gold
  stops attributing joint filings to owner 1 (486 rows, 4.43%), and
  consumer.md's holdings gate now reads "single-owner filings only".

- [Fix three name-normalizer defects before Tier B activates](issues/25-fix-person-name-normalizer-defects.md)
  — the repaired normalizer is now production code Codex's Person consumer
  imports: `edgar_warehouse/domain/policy/person_name.py`, `person-name@v2`
  (particles join the surname, `V` is a middle initial, `DATE`/`BANK`
  ineligible; `DAS`/`DO`/`DU`/`LE` kept as standalone surnames; 52 tests).
  Research 21's census re-scored: homonym false merges **1 of 11 → 0 of 11**,
  precision unchanged, LCB97.5 0.99146 → 0.99142 on n 656 — three `same`
  pairs v1 matched in breach of ticket 20's own key. No Form 3/4/5 record
  loses its shape.

## Operator directives

- **2026-09-21: nothing is deployed or re-exported until every bit of code
  is written and tested locally.** Code-owner tickets resolve against local
  evidence (bronze reads, unit/dbt-parse tests, offline measurement); the
  production steps they imply (image rollout, bootstrap SQL, `--force`
  re-parse, `dbt run --full-refresh`) are recorded on the ticket as a
  deferred sequence, not as its finish line. First applied to
  [ticket 10](issues/10-fix-proxy-executive-name-parser-leak.md).
- **2026-09-20: every source resolves every entity it carries through
  MDM** — "all sources must use MDM to resolve any entity it carries; it
  has to go through id resolution and de-duplication and merging." No
  local or derived identity key anywhere: gold's owner key
  (`'cik:' || owner_cik` else `'name:' || owner_name_norm`,
  `ownership_holdings.sql:63-67`) becomes the MDM Person id, legacy's
  per-issuer name stubs are not carried forward, and issuers, ADV firms,
  securities and funds referenced by a Person source resolve through MDM
  too — which is why ticket 05 defers an edge whose far endpoint is not
  yet accepted rather than publishing a local key.

- **2026-09-20: Tier B auto-merge bar is 99% measured precision, not
  99.9%** — "don't want to create manual work." Sent to Codex as a
  Person-kind amendment to accepted Q11:
  [proposal](../clean-mdm-person-q11-amendment-proposal/map.md).
  **Amended the same day by [ticket 20](issues/20-redecide-tier-b-after-calibration.md)**:
  the 99% stands, but its confidence bound moves from one-sided 95% to
  one-sided **97.5%** (matching research 18's method and removing the
  mismatch the Mastering Policy spec flags for Codex), and an
  identifier-namespace veto is added. The amendment to Codex is restated
  on those terms.

- **2026-09-19: "snowflake will not be restored."** No data-side
  measurement is possible; every fact this map needs comes from code
  traces (tickets 11–14, one per Person pipeline). Noted, not decided
  here: silver and gold are Snowflake-only, so this directive reaches far
  beyond Person — the platform's data layer, not just this contract.

## Not yet specified

- **Part 2B supervised persons and IARs** — not in the bulk download at
  all (research 15/16). Whether "complete Person scope" reaches them needs
  a new source, which is a capture decision for after this contract.
- **Person data in the graph and the Agent Query Surface** — ticket 05
  settled the mastered shape (two types, `IS_INSIDER` as a view, holdings
  deferred). What remains is the publication side: how the view and the
  interval list materialize into `MDM_GRAPH_EDGES`, what graph parity
  means when an edge has several intervals, and what the Agent Query
  Surface (ADR 0014, no result-level gate) may read. Sharpens with
  ticket 07 (cadence) and is settled in the spec, ticket 08.
- **Reporting-owner entities of undetermined kind** — trusts, LLCs, funds
  holding 10%: retained as deferred records outside the Person scope. Which
  future consumer (Fund Structure, Company) claims them is that consumer's
  charting, not this map's.

## Out of scope

- [Measure reporting-owner overlap once Snowflake is reachable](issues/09-measure-reporting-owner-overlap-when-snowflake-returns.md)
  — closed 2026-09-19: Snowflake will not be restored.

- Implementation, migrations, schedules, deployment — Codex/Grok's, after
  their Company gate.
- Any edit to `.scratch/clean-mdm/`, `docs/specs/clean-mdm/`, or
  `edgar_warehouse/mdm/clean/`. Disagreements go back by handover note.
- Person evidence from GLEIF or any LEI source — excluded by the MDM
  Enrichment Program; the sole-proprietor boundary stays in its workstream.
- Reopening Clean MDM's accepted Q1–Q16 merge policy.
- Legacy MDM in any form.
