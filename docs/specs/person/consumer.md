# Person — SEC multi-source consumer specification

Owning map: [Person Consumer Contract](../../../.scratch/person-consumer-contract/map.md),
sixteen resolved decision tickets (2026-09-19 → 09-20), written up here per
[ticket 08](../../../.scratch/person-consumer-contract/issues/08-write-person-consumer-spec.md).

Status: **decision-complete for the Person consumer; not implementation
complete.** Every decision below is resolved and cited; the things that are
not decided are marked *Open* and are not hidden. Nothing here authorizes
implementation — the [release gates](#release-gates) do.

**Implementation owner.** Clean MDM (`edgar_warehouse/mdm/clean/`,
`docs/specs/clean-mdm/`, Codex/Grok-owned and read-only from here). Their
[Company completion gate](../clean-mdm/company-completion.md) line 80 forbids
starting Person integration until the local Company gate passes; this spec is
the contract that integration must satisfy when it starts, not a delivery
plan. Where this spec and a Clean MDM document disagree, the disagreement is a
defect in one of them, raised by a note under `.scratch/handover/` — never by
editing their files.

**Person is not GLEIF enrichment.** The MDM Enrichment Program excludes
human-person enrichment from LEI evidence. This consumer shares that program's
[Shared Enrichment Foundation](../mdm-enrichment/shared-foundation.md) for
actors, retention, checkpoints and run evidence, and nothing else.

## Governing directive

Legacy MDM is being decommissioned (operator, 2026-09-19). This consumer
targets `mdm_v2` and the Merge Stage only. Legacy Person code is cited here
only as evidence of current behaviour, and its decommissioning is inventoried
in [ticket 22](../../../.scratch/person-consumer-contract/issues/22-decommission-legacy-person-code-and-tests.md).

**Operator principle (2026-09-20), governing everything below**: *every source
resolves every entity it carries through MDM — id resolution, de-duplication
and merging. No local or derived identity key anywhere.* Named consequences:
gold's owner key, today `party_nk` = `'cik:' || owner_cik` else
`'name:' || owner_name_norm`, surrogate-hashed into `party_key`
(`ownership_holdings.sql:63-68`, `:80`), becomes the MDM
Person id; legacy's per-issuer name stubs are not carried forward; and the far
endpoints of Person edges (issuers, adviser firms, securities, funds) resolve
through MDM too, which is why an edge whose endpoint is not yet an accepted
identity defers rather than publishing a local key.

**Snowflake will not be restored** (operator, 2026-09-19). Every figure in this
spec was measured from bronze S3, the source-layer export snapshots, or the ADV
FOIA archive — never from silver or gold.

## Vocabulary

Uses `CONTEXT.md` as written; adds nothing. **Person Identity** — "the identity
of one natural person, distinct from a Company and shared with an applicable
individual Adviser profile"; *avoid*: employer identity, **role as identity**,
same name as proof of sameness. **Mastering Policy** and **Identifier
Contract** are as defined there and in
[policy-language.md](../mdm/policy-language.md). Clean MDM's own terms —
assertion, decision, projection, deferred record, Steward, Merge Stage,
candidate assessment — are used in their sense and never redefined.

Two terms this spec uses precisely:

- **Capacity** — the kind of relationship a person holds at a company
  (`director`, `officer`, `employee`, `ten_percent_owner`, `owner`,
  `control_person`). Part of an edge's identity. Not a title.
- **Title** — the source-reported wording ("President and CEO"). A dated
  property of an edge, never part of its identity, never identity evidence.

## Source authority

Four SEC sources carry a natural person. Verified complete against
`edgar_warehouse/silver_schema.py` (2026-09-19): no other silver table does.

| Source | Grain | Person identifier | Person fields | Authority |
| --- | --- | --- | --- | --- |
| Form 3/4/5 reporting owners (`sec_ownership_reporting_owner`, `silver_schema.py:422-435`) | one row per (accession, owner_index) | `owner_cik` — an SEC filer account for the individual | name, `is_director`, `is_officer`, `is_ten_percent_owner`, `is_other`, `officer_title` | **Authoritative for capacity**: the filer restates capacity on every filing. EDGAR discards the filer-supplied name and inserts the CIK's registered name (Ownership XML Tech Spec v5.1 §4.3.2), so the name is registry-controlled |
| DEF 14A executive records (`sec_executive_record`, `:251-265`) | one row per (accession, fiscal year, executive) | none | `exec_name`, `exec_role`, six compensation figures | Richest **tenure** source — one row per named executive officer per fiscal year — and the only source naming executives who never trade. **Not a roster**: it names the highest-paid only, so an absence means nothing |
| 8-K Item 5.02 employment events (`sec_employment_event`, `:234-246`) | one row per (accession, event_index) | none | `person_name`, `exec_role`, `previous_role`, `event_type`, `effective_date`, `compensation_amount` | The only source that **states** appointment and departure dates |
| ADV Schedule A/B (`IA_Schedule_A_B` in the monthly FOIA archive) | one row per (filing, owner) | `OwnerID` — a CRD-system individual record id | `Full Legal Name`, `DE/FE/I`, `Title or Status`, `Status Acquired`, `Ownership Code`, `Control Person` | Authoritative for firm **ownership and control**, and a **complete roster** of direct owners and control persons for that filing |

Measured properties that decide the rules below:

- `OwnerID` is present on **99.7%** of Schedule A/B rows, disjoint from firm
  CRDs, stable month to month (5,322/5,322), and name-exact where IAPD
  resolves it (110/110) — **but not unique per natural person**: the issuer
  admits duplicates, and only ~54% corroborate publicly (research 16).
- `owner_cik` is present on **100%** of reporting-owner decisions (72,981 over
  14,566 distinct owner CIKs in 4,010 issuer contexts, research 17 F1). There is
  **no** genuine "one CIK, two people" case: 0 of 72,981 person decisions, upper
  bound 0.53 per 10,000 (Mastering Policy research 07, a separate study over
  104,970 rows).
- The two id-bearing sources **do not meet**: of 3,981 distinct CIKs in
  `IA_1D3_CIK`, **3** are issuer CIKs in the Form 3/4/5 corpus (research 17).
- The two name-only sources lose rows before any rule runs (research 17 F1):
  8-K is **53.2%** person-shaped and eligible (4,193 of 7,878 — the rest are
  role phrases the parser writes into `person_name`), DEF 14A **41.3%**
  (6,091 of 14,755). DEF 14A's loss is ticket 10's documented **47%** role-text
  leak plus single-token and honorific-only rows — an edgartools extractor
  defect (`edgar/proxy/html_extractor.py:857-864`, copied at
  `proxy_fundamentals.py:108`;
  [ticket 10](../../../.scratch/person-consumer-contract/issues/10-fix-proxy-executive-name-parser-leak.md)).
  Research 01 measured 97.7% plausible names in its own 8-K export snapshot;
  research 17's person-shape filter is stricter, and this spec uses the
  stricter figure.
- A name never binds across issuers: 398 of 10,042 8-K names appear under more
  than one issuer (research 01).

**Not in scope as sources**: ADV Part 2B supervised persons and IARs, which are
not in the bulk download at all (research 15/16); any non-SEC/IARD source.

## Accepted identity evidence

### Classification first: is this reporting owner a person?

Form 3/4/5 reporting owners include entities — funds, trusts and companies
holding 10%. **Rule C-J**, per owner CIK, resolved in
[ticket 03](../../../.scratch/person-consumer-contract/issues/03-decide-reporting-owner-classification.md)
and measured in research 18 (5,743 owner rows, 4,831 CIKs, 1,220 labelled):

| Step | Condition | Verdict |
| --- | --- | --- |
| 0 | no bronze `submissions.json` for the CIK | deferred |
| 1 | SEC `entityType` ∈ {`operating`, `investment`} | company — bind by CIK |
| 2-guard | single-token, person-shaped, structurally empty | deferred (a surname that is also a legal-form token) |
| 2 | unambiguous legal-form token in the name | entity of undetermined kind — terminal for Person, retained, no review |
| 3 | no token **and** structurally empty (`sic`, `stateOfIncorporation`, `ein`, `tickers`, `ownerOrg`, `fiscalYearEnd` all absent) **and** person-shaped name | **person, automatic** |
| 4 | otherwise | Steward |

Measured: person arm **841/841** (Wilson LCB 0.9955); entity arm 507/507
pooled under the post-hoc guard (LCB 0.9925); **~1.1%** of owners deferred.
Silver `owner_name` is edgartools' display reversal ("Timothy D Cook") and is
not classification evidence; rule C-J and the Person normalizer read
`owner_name_raw`, the registry form EDGAR disseminated ("COOK TIMOTHY D").
Flags, `entityType = 'other'` and deputization text are **evidence, never
deciders** — `other` is 71% person and "10%-only" is 72% entity, so neither may
decide. Category, asserted legal form and inferred kind are recorded separately
in `assertion.body` with rule id and version (`domain-model.md:41-44`); a kind
correction is review plus bounded rebuild, never a merge.

The **entity arm is gated**: its post-hoc guards must be re-measured in
production before its decisions are automatic (ticket 03).

### Binding: what may attach a source record to a Person Identity

From [ticket 02](../../../.scratch/person-consumer-contract/issues/02-decide-what-binds-a-person.md),
as amended by
[ticket 20](../../../.scratch/person-consumer-contract/issues/20-redecide-tier-b-after-calibration.md):

1. **One Person, one MDM id.** Every source identifier (`owner_cik`,
   `OwnerID`, and any future one) is a **cross-reference**, never the identity
   and never part of a composite key. A Person holds any number of them.
2. **A cross-reference id points at exactly one Person.** A second record
   carrying an already-bound id is the same Person, deterministically — that
   is how duplicate CRD records collapse. A second *Person* claiming a bound
   id is a hard veto → review.
3. **No Person is created without a match attempt.** Creation is the last
   outcome.
4. **Identifiers veto** (ticket 20). If two records carry identifiers in the
   **same namespace** with different values, the pair is vetoed: never
   auto-merged, never queued for review one at a time, recorded as a counted
   `distinct_identified` disposition. Stated as a reason — an identifier in a
   namespace whose Identifier Contract declares exclusivity is a
   *distinguishing* fact — not as a source list.
5. **Tiers**, for a record whose cross-reference ids are all unbound:

| Tier | Evidence | Action |
| --- | --- | --- |
| A | shared cross-reference id | automatic, deterministic — activates through a verified Identifier Contract (Clean MDM Q14, accepted 2026-09-20), not a precision study |
| B | compound context key (below) | automatic **only** once a held-out calibration proves ≥ 99% precision at a one-sided **97.5%** Wilson lower bound. **Not met today** |
| C | fuzzy name, or a name across different issuers | Steward review, through the candidate assessment |
| D | below the review floor | reject, disposition recorded |

**The Tier B key** (ticket 20, from research 17's 921 labelled pairs):

- same **MDM-resolved** issuer or firm identity, **and**
- surname + given name + **middle initial** — an initial matches a middle
  name, absent-on-both matches, **and**
- **no generational-suffix conflict** — `JR`/`SR`/`II`/`III`/`IV` present on
  one side only is a **conflict**, not a match. A hard veto, not a
  normalization step: 11 of 166 homonym pairs are a father and son separated
  by nothing else.

**Role and flags are evidence, never key**: requiring role consistency would
reject 33 same-person pairs and catch 10 that the name already catches
(research 17 F6; research 18 F7 found the same). The key is pure equality plus
one veto — no `name_similarity` primitive appears in it.

**Tier B is qualified for 8-K Item 5.02, and for nothing else.**
[Research 21](../../../.scratch/person-consumer-contract/research/21-tier-b-8k-extended-labelling.md)
took the census of the population research 17 sampled — all 216 within-8-K
groups and all 721 8-K rows carrying a same-issuer Form 3/4/5 anchor, 938
candidate pairs, **661 matching the fixed key**: 658 `same`, **0 different**,
1 unknown, 2 not person names. On the eligible n = 659, `n/(n+z²)` at
z = 1.96:

| Reading | Precision | LCB95 | LCB97.5 | Clears 99%? |
| --- | --- | --- | --- | --- |
| optimistic (unknown = same) | 1.00000 | 0.99591 | **0.99420** | yes |
| conservative (unknown = error) | 0.99848 | 0.99323 | **0.99146** | yes |
| settled only (n = 658) | 1.00000 | 0.99591 | **0.99420** | yes |

Cost and caveats, all measured: candidate **recall is 0.7045** — 266
known-same pairs are lost to middle-name asymmetry and 10 to the suffix veto,
a ~30% coverage loss this contract accepts in exchange for the bound; review
volume is **15.26 per 1,000** eligible 8-K records; the issuer component is a
raw CIK because MDM issuer ids do not exist yet.

**Power, not sample size, now binds.** Every one of the 657 pairs added beyond
research 17's original 281 is `same`, and after settling, the only surviving
route to a non-`same` label fires on 1 of 721 rows. More labelling moves the
bound, not what can be detected; going further needs an MDM Person id on the
8-K side or a constructed adversarial fixture set per Q11.

Activation ships **with** the three normalizer repairs research 21 measured
([ticket 25](../../../.scratch/person-consumer-contract/issues/25-fix-person-name-normalizer-defects.md)):
multi-word surnames (the key's only false merge against Form 3/4/5's 11
same-issuer homonym CIK pairs — 1 of 11 becomes 0 of 11), `V` wrongly read as
a generational suffix (discarding 241 middle initials), and `DATE`/`BANK`
missing from the eligibility vocabulary. None touches the key.

The repairs exist: `edgar_warehouse/domain/policy/person_name.py`,
**`person-name@v2`** (`parse_conformed` for EDGAR `LAST FIRST MIDDLE`,
`parse_western` for free text, `is_person_name_candidate` for eligibility,
`PersonName.key_mi` and `.generational` for ticket 20's key and veto). Tier B
activation must use it; research 17's normalizer (`v1`) is superseded (kept in
`research/17-common.py` for replay of research 21). Re-scored
on research 21's census (`research/25-rescore.json`): false merges against the
11 homonym CIK pairs **1 → 0**, ineligible rows reaching the key 2 → 0,
precision unchanged (1.0 optimistic, 0.99848 conservative); n 659 → 656, so
LCB97.5 0.99146 → **0.99142** conservative, still clear of 99%; recall
0.7045 → 0.7013, three `same` pairs lost to a now-kept middle initial `V` on
one side (2) and a surname-only row made ineligible (1).

That confirms ticket 20's suffix veto empirically: against those same 11
homonym pairs, plain `mi` merges 7, **the veto prevents 6**, and the fixed key
merges 1.

DEF 14A remains **unqualified** and binds at Tier C: only 41.3% of its rows
are person-shaped, and it activates on its own n after ticket 10 and a
re-export. ADV Schedule A/B and Form 3/4/5 are not Tier B populations at all —
their records carry identifiers, so the veto applies instead.

**Scope**: reading `IA_Schedule_A_B` is in scope. `DE`/`FE` rows never create a
Person. Firm CRD stays an Adviser-profile attribute, never a Person key — CIK
and CRD are two typed identifiers, not one mergeable key (research 15).

## Source and MDM schemas

| Concept | Home |
| --- | --- |
| Person | `mdm_v2.identity` (`kind = 'person'`) + `mdm_v2.projection` |
| Relationship | `mdm_v2.projection` (`object_type = 'relationship'`) |
| Evidence | `mdm_v2.assertion` — including compensation, which is never projected |
| Waiting edge / unclassified owner | `mdm_v2.deferred_record` (migration 027) |
| Pre-commit proposal | durable candidate assessment (migration 028, [candidate-assessments.md](../clean-mdm/candidate-assessments.md)) |
| Checkpoint | `mdm_v2.checkpoint` keyed `(consumer, source_family, publication_family)` (migration 029, [family-checkpoints.md](../clean-mdm/family-checkpoints.md)) |
| Rules | `mdm_v2.policy` body, per [policy-language.md](../mdm/policy-language.md) |

### The Person projection

From [ticket 04](../../../.scratch/person-consumer-contract/issues/04-decide-person-fields-and-privacy.md):

| Field | Content | Rule |
| --- | --- | --- |
| `legal_name` | survived verbatim | `select_by_source_rank`: SEC-registered name for an `owner_cik` > ADV `Full Legal Name` > 8-K `person_name` > proxy `exec_name` |
| `display_name` | "First Middle Last" | derived from `legal_name` by a versioned reorder rule (`name_shape@v`). EDGAR conforms names to `Last First Middle`; the rule lives once in the Mastering Policy, never in a reader — the parse is `person-name@v2` (`edgar_warehouse/domain/policy/person_name.py`); the reorder must reuse it, not re-parse |
| `name_variants[]` | every name seen: value, source, last observed | retained **on the projection** so any seen name is searchable without a join |
| identifiers | `owner_cik`s, `OwnerID`s — each with source, validity | cross-references; a Person holds any number |
| kind evidence | rule id, version, step (C-J) | separate from source category and asserted legal form |
| `roles[]` | one row per (Company/firm identity, capacity, title period): `start_date`, `end_date`, `date_basis`, `last_observed`, `sources[]`; `CONTROLS` rows carry the ADV ownership band | **derived from the same assertions as the relationship edges, under the same rule version, in the same batch** |
| `profiles[]` | `{kind: 'adviser', profile_id, crd, status, valid_from, valid_to}` | same-ID profile membership (`domain-model.md:62`); the profile owns its content |
| `last_observed` | max over roles and identifier assertions | freshness |

`roles[]` is an operator decision taken against the recommendation (read speed
over an invariant-only identity). Three guards are binding: it is derived, not
independently survived; it re-projects with the edges in one batch; and **no
matching rule may read it** — role is not identity evidence.

**Retained as source assertions, never projected**: compensation (DEF 14A's six
figures, 8-K `compensation_amount`). Queryable through assertion history and
issuer-keyed gold. Consequence: a Tier B/C misbind can attach a wrong role,
which is visible and reviewable, but never a wrong salary to a named person.

**Never captured into MDM**: reporting-owner addresses. Form 3/4/5 XML carries
`reportingOwnerAddress` and the owner's `submissions.json` carries mailing and
business addresses; the parser keeps only `address_is_care_of` and
`address_non_us` as classification evidence
([ticket 19](../../../.scratch/person-consumer-contract/issues/19-capture-ownership-parser-evidence.md)).
Bronze retains the raw artifact unchanged.

### Relationships

From [ticket 05](../../../.scratch/person-consumer-contract/issues/05-decide-person-relationships.md).
**A relationship is one mastered fact that every form contributes dated
evidence to — not one edge per form** (operator requirement). Legacy's split of
`IS_INSIDER` (Form 3/4/5) from `EMPLOYED_BY` (proxy/8-K) asserts two things
about one relationship and is not carried forward.

| Type | Endpoints | Capacities | Evidence | Status |
| --- | --- | --- | --- | --- |
| `EMPLOYED_BY` | Person → Company | `director`, `officer`, `employee` | Form 3/4/5 flags + `officer_title`; DEF 14A `exec_role`; 8-K Item 5.02 | publishes |
| `CONTROLS` | Person → Company | `ten_percent_owner`, `owner` (with ADV band), `control_person` | Form 3/4/5 `is_ten_percent_owner`; ADV `Ownership Code` / `Control Person` | publishes |
| Holdings | Person → Security | beneficial owner / reporting person; reporting period, units, direct/indirect, derivative fields | Form 3/4/5 transaction tables | **deferred** |
| `MANAGES_FUND` | Person (adviser profile) → Fund Structure | — | ADV | **deferred** |

Split by **meaning**, not by source: a 10% holder is not an employee, and Clean
MDM already separates ownership from employment at the entity level
(`domain-model.md:61` vs `:68`). `IS_PERSON_OF` is gone — same-ID Adviser
profile membership replaces it (`:62`).

**`IS_INSIDER` is not a mastered edge.** It is a published **view** over both
types filtered to Section 16 capacities, so the graph, the Decision Contract
(`serving/subject_bundle_read.py:148`) and the MDM API
(`api/routers/persons.py:59-67`) keep the name they query without a second
mastered fact.

**Edge identity**: (Person, Company, capacity). **Title is a dated property**,
not part of the key, so `"President and CEO"` on a Form 4 and `"Chief
Executive Officer"` in the proxy are one relationship with two title
assertions. Legacy's `dedup_key_fields ["source_entity_id", "target_entity_id",
"title"]` (`002_seed_data.sql:240-244`) is not carried forward.

**Holdings publish nothing until both gates pass**: a Security identity with an
enabled consumer exists (`domain-model.md:63`, `:69`), **and** holdings are
attributed only where the artifact attributes them. The SEC Ownership XML
schema gives a transaction no owner reference (`nonDerivativeTransaction` /
`derivativeTransaction`), so a transaction on a joint filing belongs to the
filing, not to one reporting owner; the only attribution is free text in
`natureOfOwnership` ("By DST Global VI, L.P.", "See footnote"). Since
[ticket 19](../../../.scratch/person-consumer-contract/issues/19-capture-ownership-parser-evidence.md)
transaction rows carry `reporting_owner_count` and `ownership_nature`. A
holdings edge may be derived only from a filing with `reporting_owner_count =
1`; joint-filing transactions (4.43% of transaction rows, 110 of 5,356 filings
in research 18's corpus) stay filing-level assertions with their
`ownership_nature` text and never publish as a Person holding. Legacy's join
on `owner_index` (`pipeline.py:1979-1980`) attributed them to owner 1 and is
not carried forward; gold `ownership_holdings` / `ownership_activity` stopped
doing so in ticket 19. Fanning a transaction out to every co-filer is ruled
out: it would put a fund's indirect position under a natural person's name.
Assertions accumulate meanwhile; the edge publishes from history.

## Temporal behavior

Each edge holds a **list of dated intervals**, not a single span. A departure
in 2015 and a re-appointment in 2019 are two intervals — never one span that
was never true.

Every date carries its **basis**: `stated` (8-K `effective_date`, ADV
`Status Acquired`) or `observed` (Form 3/4/5 `period`, DEF 14A `fiscal_year`).
`end_date` is null unless a filing said the relationship ended; `last_observed`
carries freshness. "Still serving" and "stopped filing" are therefore never
conflated.

**What closes an interval**, and nothing else does:

1. A stated 8-K Item 5.02 departure → `date_basis = stated`,
   `end_date = effective_date`.
2. A later Form 3/4/5 from the same issuer whose owner row **omits** a capacity
   flag the person previously carried → `observed` end at that filing's event
   date. These forms restate capacity on every filing, so omission is a
   statement.
3. Absence from a later ADV Schedule A/B filing where the person appeared
   before → `observed` end at that filing's date. The schedule is a complete
   roster.

**DEF 14A absence closes nothing** — it names only the highest-paid executives.
**Silence closes nothing, ever**: a source that simply stops filing leaves
`end_date` null. Only the monthly reconciliation may evaluate closers 2 and 3
(see [cadence](#cadence-and-processing)), because both need a complete later
filing set.

Legacy closed `IS_INSIDER` only when properties differed
(`pipeline.py:658-720`) and `HOLDS` on `shares_owned_after == 0`
(`:582-656`); nothing closed by absence.

## Conflict and review states

- **Rank**: `stated` outranks `observed`, expressed as `select_by_source_rank`
  — not a source-priority table, because the distinction is assert-versus-
  observe, not trust.
- **All comparison is on event dates**, never filing dates. A Form 4 with
  `period` 2024-03-15 filed 2024-06-15 is consistent with a stated 2024-03-31
  departure: ordinary reporting lag is not a conflict.
- **A real contradiction** — an affirmative capacity whose *event date* falls
  after a stated end — does **not** silently reopen the interval. It raises a
  field-level conflict for a Steward, who either rescinds the end or opens a
  new interval. Same-rank disagreement resolves by the later event date.
- **Deferred, not dropped**: an edge whose far endpoint is not an accepted
  identity is held as a deferred record (migration 027) naming the endpoint and
  the reason, and publishes from history the first time that endpoint is
  accepted with its consumer enabled. Covers unaccepted issuer Companies,
  unaccepted ADV firms, holdings and `MANAGES_FUND`. Legacy dropped these
  silently (`pipeline.py:1890`).
- **Steward decisions** carry actor and reason; `commit_batch` rejects a
  decision without them (foundation).

## Cadence and processing

From [ticket 07](../../../.scratch/person-consumer-contract/issues/07-decide-cadence-and-backfill.md).

| Job | Does | Cadence |
| --- | --- | --- |
| **Person Daily Refresh** | on the issuers that execution touched only: bind new records, open and extend intervals, publish edges. **Never rematches the universe** | daily, with `daily_incremental` (`cron(0 12 ? * MON-SAT *)` = 8am ET) |
| **Person Candidate Backstop** | re-evaluate deferred records and Tier C candidates: owners with no `submissions.json` (~1.1%), edges waiting on an endpoint, unresolved names | weekly |
| **Person Full Reconciliation** | complete roster comparison and source-to-MDM parity; **the only job permitted to close an interval by absence** | monthly, keyed to the ADV FOIA archive's release |

ADV Schedule A/B arrives as a whole monthly file (`FetchAdvBulk`, Stage 1C, not
CIK-scoped), which sets the reconciliation period. Confining "close by absence"
to that job means a late or out-of-order filing can never retire a
directorship on the daily path.

**Initial backfill is bounded by evidence class, not company count:**

| Wave | Scope | Gate to enter |
| --- | --- | --- |
| 1 | every reporting owner and every ADV Schedule A/B row binding at **Tier A**, plus rule C-J's automatic person arm | none — deterministic; ~100% of both id-bearing sources; empty review queue |
| 2 | rule C-J's **entity** arm | its post-hoc guards re-measured in production |
| 3 | 8-K Item 5.02 (4,147 eligible rows under `person-name@v2`; 4,193 under v1) | **cleared** by research 21 (n = 659, LCB97.5 0.99146 conservative); under `person-name@v2`, n = 656, LCB97.5 **0.99142** ([ticket 25](../../../.scratch/person-consumer-contract/issues/25-fix-person-name-normalizer-defects.md)), which ships in the same release |
| 4 | DEF 14A (6,091 eligible rows under the old parser) | ticket 10 resolved on bronze (99.04% plausible, 17,371 rows); [ticket 26](../../../.scratch/person-consumer-contract/issues/26-strip-footnote-markers-and-title-fragments-from-proxy-names.md) residues, then its own Tier B measurement |

Waves are gated on evidence, never time-boxed. Company bounded its first slice
by cohort because GLEIF matching was unproven; Tier A binds without judgment,
processing all of it is no riskier than a tenth, it yields the complete Person
spine that later waves attach to, and a per-issuer cohort would split people
who serve at several issuers.

## Replay and recovery

**Replay re-enters at the pre-merge candidate stage** (operator, 2026-09-20),
not at re-projection. Re-running survivorship over already-merged state can
only correct projected values, never a wrong **binding** — and binding is
exactly what a rule change (rule C-J, the Tier B key, the identifier veto)
alters. The unit of replay is: source assertions → normalization → candidate
generation → decision → commit → projection.

This makes the durable candidate assessment (migration 028) a **requirement**
of this contract, not a preference.

**Checkpoints** are per `(consumer, source_family, publication_family)`
(migration 029), on the durable artifact: `accession_number` for Form 3/4/5,
DEF 14A and 8-K; the archive release month for ADV Schedule A/B. A missed daily
run needs no special handling — the next run's window widens to the unprocessed
accessions, since SEC artifacts are additive and immutable. A gap that cannot
be proven contiguous does **not** move the watermark; it escalates to the
monthly reconciliation, which sees a complete population.

**A policy digest change triggers a bounded rebuild from the pre-merge stage**
over the identities the changed rules can reach, with the computed scope
recorded in run evidence rather than defaulting to "everything". This fixes for
Person what [policy-language.md](../mdm/policy-language.md) §11 leaves Open.

**Ids survive replay:**

- unchanged decision → **same id**, always;
- **split**: the id stays with the records holding the surviving authoritative
  identifier; the rest get new ids; a `split` disposition names both sides, the
  rule id and version, and the run;
- **merge**: the survivor is chosen by the same identifier rule; the loser is
  **retired with `superseded_by`**, never deleted;
- retired and split ids stay resolvable **forever** — a consumer holding an old
  id gets an answer, not a 404, which is what makes replay safe for the graph's
  published generations.

The count of splits a new rule version causes is exactly how much the previous
version over-merged.

## Observability

Per run: records read, normalized, deferred, total (Clean MDM's
`source_accounting` invariant); classification verdicts by rule step, including
deferred owners; candidates by tier and disposition, including
`distinct_identified` vetoes; Persons created, bound, split, merged, retired;
intervals opened, extended, closed **by closer type**; edges published and
edges blocked **by endpoint kind** (so "how much is waiting on Security" is a
number); conflicts opened and closed; checkpoint per family before and after.

Alert on: a family checkpoint unchanged past its cadence + 24 h; any automatic
Tier B decision while Tier B is unactivated (should be impossible — alert on
the invariant); any Person projecting a compensation or address field (likewise);
any duplicate active cross-reference binding; deferred-record queue growth
without a backstop run.

*Open (foundation)*: metric names and SLO thresholds.

## Security

The foundation's actors and roles, no additions, **no new Postgres role**
(`shared-foundation.md:248`). Steward for this consumer is a named person while
Tier B is unactivated; no deterministic rule is authorized as Steward for a
Person identity decision.

**Privacy class: public record, no redaction.** Every projected field is public
— SEC filings and IARD. The Person projection is readable by any consumer that
can read Company. What the platform owes a natural person is not to manufacture
new facts about them, and to be able to stop publishing. Four structural
commitments, enforced as release gates:

1. **No non-public field enters the master** — addresses are not read;
   compensation is retained, never projected.
2. **No derived personal attribute is ever projected** — no inferred age,
   gender, ethnicity, residence, or net worth from holdings.
3. **No join to a non-SEC/IARD source** without a new consumer contract.
4. **Takedown path**: a Steward may retire a Person's projection — masked
   `display_name`, roles hidden, assertions kept — on a recorded decision with
   actor and reason, using the existing decision machinery.

The Agent Query Surface (ADR 0014) exposes raw SQL over gold, graph and MDM
with no result-level gate and defines no person-specific redaction. That is
noted, not solved here: see [Open items](#open-items).

## Retention

The foundation's contract (`shared-foundation.md:270-277`): assertions,
decisions, projection history, dispositions, deferred records, run lineage and
deletion records are permanent; only superseded raw source bytes are deletable.

**A Person who stops appearing in filings is retained unchanged.** No automatic
expiry, no dormancy state, no automatic masking — the underlying filings never
go away, and "who was on this board in 2012" must stay answerable. Freshness is
readable from `last_observed`. Retirement is only ever a Steward takedown
decision, never a timer.

## Costs

Sizing inputs, measured (research 17, 18): 72,981 reporting-owner decisions
over 14,566 distinct owner CIKs; 79,768 ADV Schedule A/B rows; 4,193 eligible
8-K rows; 6,091 eligible DEF 14A rows; ~1.1% of owners deferred at
classification. Classification needs **zero SEC requests** once ticket 19 feeds
it the bronze `submissions.json` — 4,831/4,831 owner CIKs already had one.

*Open*: runtime, memory and storage per wave, and the incremental cost of the
monthly reconciliation, which are measurable only against Clean MDM's
implementation. Approved cost is a release gate.

## Migration and rollback

**No legacy Person ID crosswalk**
([ticket 06](../../../.scratch/person-consumer-contract/issues/06-decide-legacy-person-id-crosswalk.md)).
Legacy Person ids are dropped, not mapped: legacy MDM Postgres is being
decommissioned, silver's `mdm_entity_id` and the graph's person nodes live only
in a Snowflake that will not be restored, the MDM API is undeployed, and gold
never used them. The ids are not worth carrying on their merits either — the
legacy fuzzy path's context check can never pass, so `REVIEW` bound anything
scoring Jaro-Winkler ≥ 0.80 across the whole table with no human gate
(`resolvers/base.py:268-288`), under a normalizer written for company names.

**What does carry is human judgment, as evidence**: resolved
`mdm_match_review` rows and `_merge_entities` tombstones are harvested as
source assertions — "a Steward said these two records are the same person" —
and re-adjudicated under the current rules. Whether that store is still
reachable is Open; the table may be empty, since those rows are queued only
under `reconciliation_mode=True` (`base.py:263-266`).

Silver's `sec_ownership_reporting_owner.mdm_entity_id` and
`sec_adv_filing.mdm_entity_id` are **frozen as legacy**: never read, never
rewritten by Clean MDM. Dropping the columns is the silver owner's call
(ticket 22).

**Rollback**: a wave is reversible because every proposal is a durable
candidate assessment and every id change is a recorded disposition — revoking a
wave's bindings restores the prior projection and preserves the decision chain.
Retired ids stay resolvable, so a rollback never breaks a consumer's reference.

## Tests

Beyond the foundation's:

| Level | Proves |
| --- | --- |
| Unit | Rule C-J reproduces research 18's primary labelled corpus exactly — 841/841 person, 353/353 entity, 26 deferred — from the frozen `18-sample.jsonl` fixture; the 507/507 entity figure is that corpus pooled with `18-extension-sample.jsonl` |
| Unit | Classification never reads a flag, `entityType='other'` or deputization text as a decider |
| Unit | The Tier B key vetoes a generational-suffix mismatch, matches a middle initial to a middle name, and ignores role/flag entirely |
| Unit | Two records with different values in one identifier namespace never merge, and record `distinct_identified` |
| Unit | No matching rule reads `roles[]`; no projection carries a compensation or address field |
| Unit | `display_name` reorder is versioned and reproduces "Last First Middle" → "First Middle Last" on the EDGAR-conformed corpus |
| Integration (PG16) | A title change produces one edge with two title assertions, not two edges |
| Integration | A departure and a later re-appointment produce two intervals; no query returns the gap as served |
| Integration | A Form 4 whose `period` predates a stated departure does not raise a conflict; one whose `period` follows it does, and does not reopen the interval |
| Integration | DEF 14A absence closes nothing; ADV roster absence closes only in the monthly job |
| Integration | An edge with an unaccepted endpoint creates a deferred record and no edge, then publishes from history when the endpoint is accepted |
| Replay | Rerunning a frozen cohort from the pre-merge stage yields identical Persons, ids, edges and hashes |
| Replay | A rule-version change that splits a Person keeps the id on the side holding the authoritative identifier, mints a new id for the other, records the disposition, and leaves the retired id resolvable |
| Recovery | A missed daily run is absorbed by the next run's widened window; an unprovable gap does not move the watermark and escalates to reconciliation |

Synthetic fixtures are labelled and never count as calibration evidence.

## Release gates

All required:

1. Rule C-J reproduces its measured corpus, and its **entity arm's post-hoc
   guards are re-measured in production** before entity decisions are automatic.
2. **Zero** automatic Tier B decisions on any population that has not itself
   cleared ≥ 99% at a one-sided 97.5% lower bound. 8-K is cleared
   (research 21, n = 659; re-scored under `person-name@v2`, n = 656,
   LCB97.5 0.99142 conservative); DEF 14A and every id-bearing source are not, and
   bind at Tier C or through the identifier veto. Tier B activation requires
   the ticket 25 normalizer (`person-name@v2`) in the same release.
3. **Zero** name-only automatic binds; **zero** duplicate active
   cross-reference bindings.
4. Complete provenance on every projected value, role row and edge.
5. Deterministic replay of a frozen cohort **from the pre-merge stage**.
6. Independent, fail-closed checkpoints per family (migration 029).
7. Privacy gates 1–3 verified by test; the takedown path exercised end to end.
8. Holdings publish only after a Security identity with an enabled consumer
   is in place, and only from single-owner filings (`reporting_owner_count =
   1`, ticket 19); joint-filing transactions never publish as a Person
   holding.
9. Downstream parity for the same generation, including the `IS_INSIDER` view.
10. Rollback proof, including that a retired id stays resolvable.
11. Approved runtime / memory / storage / request cost.
12. Release Owner GO.

Plus the foundation's own gates, inherited.

## Dependencies

| Dependency | State |
| --- | --- |
| Clean MDM Company completion gate (`company-completion.md:80`) | Person integration may not start before it passes |
| Durable candidate assessments (migration 028) | **accepted and implemented** by Clean MDM Q13 — required by this contract's replay rule |
| Per-family checkpoints (migration 029) | **accepted and implemented** |
| Rules-as-data policy body + Identifier Contract | **accepted for Company** as Q14 (2026-09-20); Person needs the same activation path for Tier A |
| Person amendment to Q11 — ≥ 99% at one-sided 97.5%, with the identifier veto | **open with Codex**; Company's Q11 (99.9% at 95%) is explicitly not to be applied to other kinds |
| Ticket 10 (proxy name parser) | **done** — full bronze re-parse, 99.04% plausible, attribution 60/60; [ticket 26](../../../.scratch/person-consumer-contract/issues/26-strip-footnote-markers-and-title-fragments-from-proxy-names.md) residues block DEF 14A Tier B |
| Ticket 19 (ownership parser evidence, incl. the joint-filing marker `reporting_owner_count`) | **done** — classification evidence from bronze with zero SEC requests; holdings still wait on Security identity |
| Ticket 21 (8-K labelling to n ≥ 381) | **done** — research 21 cleared 8-K at n = 659 |
| [Ticket 25](../../../.scratch/person-consumer-contract/issues/25-fix-person-name-normalizer-defects.md) normalizer repairs | **done** — `person-name@v2` (`edgar_warehouse/domain/policy/person_name.py`); Tier B activation must use it |
| Security identity + consumer | blocks holdings |
| Fund Structure identity + consumer | blocks `MANAGES_FUND` |

## Open items

1. **Graph publication side**: how an interval list and the `IS_INSIDER` view
   materialize into `MDM_GRAPH_EDGES`, and what graph parity means when an edge
   has several intervals.
2. **Agent Query Surface**: ADR 0014 exposes raw SQL with no result-level gate
   and no person-specific rule. Whether the Person projection needs a surface
   restriction is a decision for that ADR's owner, named here.
3. **Legacy steward decisions**: whether legacy MDM Postgres is still reachable
   and whether any human person decision exists there to harvest.
4. **Cost** per wave and for the monthly reconciliation.
5. **Foundation Opens** inherited: IAM for the Temporary Bronze Stage and
   Source Artifact Archive; metric names and SLO thresholds.

## Non-goals

- Implementation, migrations, schedules, deployment — Clean MDM's.
- Any edit to `.scratch/clean-mdm/`, `docs/specs/clean-mdm/` or
  `edgar_warehouse/mdm/clean/`.
- Person evidence from GLEIF or any LEI source.
- Reopening Clean MDM's accepted Q1–Q16 merge policy, beyond the one Person
  amendment named in Dependencies.
- Legacy MDM in any form.
- ADV Part 2B supervised persons and IARs — a capture decision, not this
  contract's.

## Evidence

Every decision above traces to one resolved ticket on the
[Person Consumer Contract map](../../../.scratch/person-consumer-contract/map.md).

| Decision | Ticket | Measurement |
| --- | --- | --- |
| Name-only sources cannot bind on name | 01 | research 01 — 398/10,042 names cross-issuer |
| Four pipeline code traces | 11, 12, 13, 14 | — |
| CRD vs CIK are two typed identifiers | 15 | research 15 |
| `OwnerID` is a CRD individual record id | 16 | research 16 — 5,322/5,322 stable, 110/110 name-exact |
| What binds a Person; tiers A–D | 02 | — |
| Reporting-owner classification (rule C-J) | 03 | research 18 — 841/841 person, 1,220 labels |
| Classification precision study | 18 | research 18 |
| Projection, privacy, retention | 04 | — |
| Relationships, intervals, closers | 05 | — |
| No legacy crosswalk | 06 | verified holders, 2026-09-20 |
| Cadence, backfill waves, replay, id survival | 07 | — |
| Tier B calibration | 17 | research 17 — 921 labelled pairs |
| Tier B qualified for 8-K | 21, 25 | research 21 — 938-pair census, n = 659, LCB97.5 0.99146 conservative; v2 re-score n = 656, 0.99142 (ticket 25) |
| Tier B redefinition: identifier veto, 97.5%, the key | 20 | research 17 |
