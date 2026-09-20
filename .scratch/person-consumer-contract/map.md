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

## Notes

- **Why now**: Codex's `docs/specs/clean-mdm/company-completion.md` line 71
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

## Operator directives

- **2026-09-19: "snowflake will not be restored."** No data-side
  measurement is possible; every fact this map needs comes from code
  traces (tickets 11–14, one per Person pipeline). Noted, not decided
  here: silver and gold are Snowflake-only, so this directive reaches far
  beyond Person — the platform's data layer, not just this contract.

## Not yet specified

- **ADV Schedule A/B owners** — research 15 settled the fact: they are
  *in* the archive the platform already downloads (`IA_Schedule_A_B`,
  unread). "Complete Person scope" therefore needs a scope decision —
  read that member (a parser extension, with `OwnerID`'s meaning still
  unpublished) or explicitly exclude — which ticket 02 Q2 now poses. Part
  2B supervised persons and IARs are *not* in the bulk download at all.
- **Name-only matching calibration** — whatever ticket 02 allows for proxy
  and 8-K names will need the same independent-holdout proof Clean MDM
  demands for Company (Q11 bar). Whether that's a Person research corpus
  like the GLEIF 1,000-company cohort, and who freezes it, waits on 02.
- **Person data in the graph and the Agent Query Surface** — `IS_INSIDER`
  and `HOLDS` are the heaviest-used graph edges; what the Person consumer
  owes downstream consumers (parity, redaction at the API) sharpens after
  tickets 03 and 04.

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
