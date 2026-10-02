# Relationship inventory for Clean MDM (ticket 06, step 1)

Date: 2026-10-01 ET. Read-only. No network, no code run. Ticket:
`.scratch/platform-validation/issues/06-relationship-rules.md`.

The operator ruled that relationships are mastered with the entities
(`.scratch/onboarding/sec.submissions.person/onboarding-log.md:456-475`).

## Five facts that shape everything below

1. **The SEC form parsers are gone.** `ownership.py`, `adv.py`,
   `proxy_fundamentals.py`, `item_502.py`, `thirteenf.py`,
   `subsidiary_exhibits.py` and `auditor_evidence.py` were deleted in commit
   `7f753322` (#764). Their silver tables survive in
   `edgar_warehouse/silver_schema.py` as "schema only": declared, nothing
   writes them. Old code is cited as `7f753322^:<path>`.
2. **Locally there is no form bronze.** `~/.local/share/edgartools/clean-mdm/`
   holds SEC submissions and reference files
   (`captures/sec.submissions.company/all-76230/bronze/`) and the GLEIF Golden
   Copy with its relationship file (`research/gleif-20260911-1600/`). No
   Forms 3/4/5, DEF 14A, 8-K, ADV or 13F.
3. **Only GLEIF has a relationship mapping, and it cannot merge yet.**
   `rules/sources/gleif/source.yaml:118-162` maps two GLEIF types. But
   Company's source list (`rules/merge/kinds/company.yaml:11-13`) lacks
   `gleif.relationships.v1`. `merge.py:40-49` fails a batch that brings a
   Company source not on that list. Also, the edge's start is the reading's
   own subject (`relationships.py:98-101`). For GLEIF that subject is the
   relationship record, keyed start, end and type (`source.yaml:145-148`).
   No matching rule joins that record to a Company, and a relationship
   record becomes a link only once one does
   (`skills/data-onboarding/REFERENCE.md:164`). The SEC sources map no
   relationships at all.
4. **The engine does not follow the Person spec yet.** `relationships.py`
   was written before the Person spec. The spec already decided each point
   below; the engine must catch up:
   - It refuses an edge with no stated start (`relationships.py:114-116`).
     The spec allows dates that are only observed (`docs/specs/person/consumer.md:345-350`).
   - Its edge identity is a hash of every field: dates, title, properties
     and scope (`relationships.py:140-141`). The spec says identity is
     Person, Company and capacity; title is a dated property (`consumer.md:315-318`).
   - It keeps one start and end per edge. The spec wants a list of
     intervals, each with its date basis (`consumer.md:342-350`;
     `CONTEXT.md:37-39`).
   - It knows `INSIDER_OF` but not `CONTROLS` (`relationships.py:15-16`).
     The spec masters `EMPLOYED_BY` and `CONTROLS` and makes `IS_INSIDER` a
     view (`consumer.md:299-313`).
   - Per record, only the newest reading's relationships survive
     (`survivorship.py:109`). So the record key decides whether history
     builds up: one record per filing keeps it; one record per person would
     overwrite it.
5. **Profile-gated types cannot pass today.** `MANAGES_FUND`, `AUDITED_BY`
   and the GLEIF fund links need a profile on an end
   (`relationships.py:13,18-23,32-49,126-137`). No rule maps a profile
   (`grep profiles: rules/` finds none). Every such edge would wait as
   `missing_endpoint_profile`.

How it is stored, once it works: the source reading keeps the stated
relationships in its body (`edgar_warehouse/mdm/migrations/001_mdm.sql:22-34`,
comment at `:1592`). The merge projects each accepted edge into
`mdm.current_record` with `object_type = 'relationship'` (`001_mdm.sql:85-91`;
`merge.py:609-620`). Refused edges become open review records
(`merge.py:621-636`).

## The inventory

Status words: **spec** = described in a spec or the glossary only; **engine**
= a type in `relationships.py` CONTRACTS; **mapped** = a source contract
fills it; **on** = merged and approved. Nothing is **on** today.

### Person and Company

| Type, direction, kinds | Sources today | How each end is found | Time and identity | Status |
|---|---|---|---|---|
| **EMPLOYED_BY**: Person → Company. Capacities director, officer, employee (`CONTEXT.md:33-35,109-111`) | Forms 3/4/5 owner flags and `officer_title`; DEF 14A `exec_role`; 8-K Item 5.02 (`consumer.md:74-76,299`). Silver: `sec_ownership_reporting_owner` (`silver_schema.py:425-453`), `sec_executive_record` (`:252-266`), `sec_employment_event` (`:235-247`), all schema only | Person: Forms 3/4/5 carry `owner_cik`, so it is deterministic. DEF 14A and 8-K give a name only, so they need a match. Tier B is qualified for 8-K only (`consumer.md:186`). Company: the issuer CIK is in the XML (`7f753322^:edgar_warehouse/parsers/ownership.py:82`), but the silver owner table has no issuer column, so it joins by accession. DEF 14A and 8-K carry the filer `cik` | Stated dates: 8-K `effective_date`. Observed dates: the Form 4 `period` and the DEF 14A fiscal year (`consumer.md:345-347`). Closers: an 8-K departure, a later Form 3/4/5 that drops the flag, nothing else (`:352-366`). Spec identity: Person, Company and capacity (`:315`) | spec + engine (`relationships.py:15`); not mapped; no capture |
| **CONTROLS**: Person → Company. Capacities ten percent owner, owner, control person | Form 3/4/5 `is_ten_percent_owner`; ADV Schedule A/B ownership code and control person (`consumer.md:77,300`). Schedule A/B has no silver table | Forms 3/4/5: CIK, deterministic. ADV: `OwnerID`, a CRD individual id. It is not unique per person, so it needs a match (`consumer.md:80-84`). Firm: CRD, which no rule maps | ADV `Status Acquired` is a stated date. Schedule A/B is a full roster, so absence closes (`:360-362`) | spec only. Missing from `relationships.py` CONTRACTS |
| **INSIDER_OF / IS_INSIDER**: Person → Company | Same as above | Same as above | The spec makes it a view, not a mastered edge (`consumer.md:309-313`) | engine type (`relationships.py:16`) that the spec retires |
| **Person acts for an entity**: trustee, attorney-in-fact, "ET AL" lead. Person → Company or trust | Filer names (see below); Form 3/4/5 signatures and remarks (`filing_remarks`, `other_text`, `silver_schema.py:425-453`); ADV Schedule A/B | The trust is the filer CIK, so that end is deterministic. The person is a name only | Not dated in a name | Ruled necessary (`onboarding-log.md:458-468`); no type, no glossary term |

### Company hierarchy

| Type, direction, kinds | Sources today | How each end is found | Time and identity | Status |
|---|---|---|---|---|
| **Accounting Direct Parent**: Company → Company (`CONTEXT.md:121-123`). GLEIF `IS_DIRECTLY_CONSOLIDATED_BY` | GLEIF RR. The local Golden Copy has 126,688 such records | LEI at both ends, all records (975,442 of 975,442 nodes are LEIs). Each end joins a Company through the live SEC–GLEIF matching rules (`company.yaml:233-300`). The reader drops a record unless both ends are in the approved Company scope (`gleif_source.py:428-429`) | Stated `StartDate`/`EndDate`, plus a status (`gleif_source.py:431-451`). Engine identity: a hash of all fields. One parent per scope and time; two overlapping parents are refused (`relationships.py:157-173`) | mapped (`source.yaml:149-162`), parsed and unit-tested on synthetic claims (`tests/mdm/test_clean_gleif_source.py:285-319`); not mergeable (fact 3) |
| **Reported Ultimate Parent**: Company → Company (`CONTEXT.md:213-215`). GLEIF `IS_ULTIMATELY_CONSOLIDATED_BY` | GLEIF RR: 132,877 records | Same as above | Same as above | mapped, not mergeable |
| **Calculated Ultimate Parent**: derived | Built from direct parent edges (`relationships.py:208-243`) | Follows from the direct edges | Computed as of the run time; a disputed link leaves it unknown (`:229-231`) | engine only |
| **GLEIF reporting exceptions**: why a parent is missing | GLEIF repex file | LEI | Stated reason. Not a relationship (`research/10-gleif-relationship-routing.md`, Reporting exceptions) | mapped as `gleif.reporting_exceptions.v1` (`source.yaml:163-192`) |
| **Ownership Parent**: Company → Company, several allowed (`CONTEXT.md:117-119`) | Exhibit 21 (`sec_subsidiary_evidence`, `silver_schema.py:482-497`, schema only; writer removed: `7f753322^:edgar_warehouse/application/subsidiary_exhibits.py`); Schedules 13D and 13G have no table | Parent: the registrant CIK. Subsidiary: legal name and jurisdiction only, so it needs a match. A similar name never proves ownership (`CONTEXT.md:119`) | Exhibit 21 states an `effective_date`. ADR 0008 puts this family under "property differs from prior" | engine (`relationships.py:24`); not mapped |
| **IS_INTERNATIONAL_BRANCH_OF**: Branch → head office (`CONTEXT.md:113-115`) | GLEIF RR: 1,959 records | LEI | Stated | engine (`:29`). Not in the GLEIF type map, so it is set aside as `unsupported_relationship_type` (`adapters.py:322-325`). Branch is a probable kind only (`gleif/source.yaml`, `probable_kind_values`) |
| **AUDITED_BY**: Company → audit-firm Company, per engagement (`CONTEXT.md:105-107`) | Auditor report evidence (`sec_auditor_report_evidence`, `silver_schema.py:110-129`), PCAOB firms (`:454-464`), `sec_accounting_flag.auditor_pcaob_id` (`:18-37`). All schema only; writer removed (`7f753322^:edgar_warehouse/application/auditor_evidence.py`) | Client: the registrant CIK. Auditor: the PCAOB firm id, which no rule maps; a name otherwise | Audited period and report date are stated per engagement | engine, needs an Audit Firm profile on the auditor (`relationships.py:13`); not mapped |

### Funds and securities

| Type, direction, kinds | Sources today | How each end is found | Time and identity | Status |
|---|---|---|---|---|
| **MANAGES_FUND**: adviser (Company or Person) → Fund Series (`CONTEXT.md:81-83`) | N-CEN (no table, no reader); ADV Schedule D private funds (`sec_adv_private_fund`, `silver_schema.py:89-109`, schema only) | Adviser: CRD (`adviser_crd_number`). Fund: `private_fund_id`. Neither has an Identifier Contract | ADV period roster, "periodic snapshot diff" (`docs/adr/0008-name-relationship-closing-patterns.md`) | engine, needs adviser and fund profiles (`relationships.py:18-23`); Person side deferred (`consumer.md:302`) |
| **GLEIF Fund Link**: `IS_FUND-MANAGED_BY` (150,982), `IS_SUBFUND_OF` (73,834), `IS_FEEDER_TO` (1,381) (`CONTEXT.md:125-127`) | GLEIF RR | LEI. Needs a Fund Structure kind, which does not exist | Stated | engine (`relationships.py:32-49`). Not mapped; routed "later Fund consumer" (`research/10-gleif-relationship-routing.md`) |
| **Fund Series → Fund Company** (a series of a trust) | Series ids in SEC filings; "a series of" in filer names (below) | Series id; parent CIK. In names, the parent is a name only | — | glossary only (`CONTEXT.md:73-79`); no type |
| **ISSUED_BY**: Security → issuer (`CONTEXT.md:29-31`; ADR 0015) | 13F issuer name (`sec_thirteenf_holding`, `silver_schema.py:511-532`, schema only) | Security: CUSIP. Issuer: a name, matched to an existing Company or its alias; no match writes no edge and mints no Company (`.scratch/security-mastering/issues/02-issued-by-a-mastered-company.md`) | No closing needed (ADR 0008) | engine (`relationships.py:14`). `securities.py` publishes Securities but writes no edge (`securities.py:11-30`) |
| **Holdings**: Person, Company or Fund Series → Security (`CONTEXT.md:101-103`) | 13F (manager CIK, CUSIP); Form 3/4/5 transactions (`silver_schema.py:384-424`) | 13F: manager CIK and CUSIP, both deterministic. Form 4: only when `reporting_owner_count = 1` (`consumer.md:322-336`) | One period and capacity. Closed by zero shares or a period diff (ADR 0008) | engine `HOLDS` (`relationships.py:17`); Person side deferred (`consumer.md:301`) |
| **VENUE_OPERATOR, VENUE_SEGMENT_OF** | No source | — | — | engine only (`relationships.py:30-31`) |

## Relationships stated inside names

Counted over the 76,230 SEC submissions names in
`~/.local/share/edgartools/clean-mdm/research/rebuilt-2026-09-28/cm08-sec-scan.jsonl`
(word-bounded, case-insensitive grep):

| Pattern | Count | Example | What the two ends are |
|---|---|---|---|
| "a series of <parent>" | 1,996 (1,995 typed `other`) | "Pirouette D 2026 I, a series of Capitalize Investments LLC" | Series: the filer CIK. Parent: a name only within this capture. About 450 distinct parents; the top one is CGF2021 LLC with 522 series. Within this capture, 0 parent names match a filer name exactly (upper-cased). A parent may have a CIK outside it |
| "Trustee" | 26 | "David BH Williams, Trustee UAD The Helen Charles Williams 2004 Trust" | Trust: the filer CIK. Trustee: a person name only |
| "FBO" | 9 | "RC Kemper Jr. Irrevocable Dynasty Trust FBO John Mariner Kemper" | Beneficiary: a person name only |
| "dba" | 24 | "Lester Murray Antman dba SimplyRich" | A person or firm and a trade name. Possibly one identity with an alias |
| "ET AL" | 10 | "WATSA V PREM ET AL", "COX ENTERPRISES INC ET AL" | A group filer. The other members are named only in 13D/13G and Forms 3/4/5, which are not captured |
| "General Partner" | 29 | "Lightspeed General Partner X, L.P." | A weak hint that it is the GP of a fund of a similar name |

What these would need:

- A name-reading step that splits the name into its parties and a role word,
  shown as a Primitive or Named Convention with its own tests (`CONTEXT.md:189-195`).
- The filer's CIK is known, but an edge also needs an accepted identity of
  the right kind (`relationships.py:108-113`). Today neither kind accepts
  these filers. All 1,996 series filers have no SIC and no category in this
  capture, so Company's step 10 cannot accept them and they fall to step 11,
  held back (`rules/merge/kinds/company.yaml:190-211`). The Person rule holds
  back any name with a legal-form word such as LLC or TRUST
  (`rules/merge/kinds/person.yaml:64-73,125-250`).
- The other end is a name, so it must go through a matching rule like any
  other name. Otherwise it waits.
- Person feed 1 keeps the name as written (`onboarding-log.md:470-475`). The
  reading belongs to the relationship feed.

## Open questions for the operator

Already decided, so not asked again: `CONTROLS` and `EMPLOYED_BY` as the
mastered types, `IS_INSIDER` as a view, identity as Person, Company and
capacity, and observed dates allowed (`consumer.md:299-318,345-350`). For
GLEIF: both ends must be accepted, and direct and ultimate parents are
separate types (`.scratch/gleif-company-augmentation/research/10-gleif-relationship-routing.md`).

1. Does the Person identity shape carry over to Company types, for example child, parent and scope for an accounting parent?
2. Does each Form 3/4/5 filing become its own source record, so its relationship history builds up?
3. Is "person acts for an entity" (trustee, attorney-in-fact) one type with a capacity, and what is it called?
4. What kind is a series LLC, and what kind is a trust, given that neither kind accepts them today?
5. Is "a series of" a Fund Series → Fund Company link, or a Company → Company link until a Fund kind exists?
6. When a series parent has no CIK in our capture, does the link wait with the parent's name kept?
7. Is "X dba Y" one identity with Y as an alias, or two identities with a link?
8. Should "ET AL" filers stay single Companies, with the members linked only from 13D/13G later?
9. Should Ownership Parent wait until Exhibit 21 or 13D/13G is captured again?
10. Who wins when a GLEIF parent and an SEC ownership statement disagree? Today they are separate types and never compete.

## Recommended first pair

**Person: Forms 3/4/5 reporting owner → issuer, as EMPLOYED_BY and CONTROLS.**
- Both ends carry a CIK, so matching is deterministic. The Person CIK
  matching rule is already approved (`rules/merge/kinds/person.yaml:107-121`).
  The issuer CIK joins a Company through the live Company CIK matching rule
  (`rules/merge/kinds/company.yaml:218-232`).
- The forms restate capacity on every filing. So they can close an interval
  as well as open one (`consumer.md:356-359`).
- They are the most common Person source: 72,981 owner decisions over 14,566
  owner CIKs (`consumer.md:85-88`).
- Prerequisites: capture Forms 3/4/5 bronze, and write a new reader or source
  contract. The old parser was deleted (`7f753322^:edgar_warehouse/parsers/ownership.py`),
  and no form files are local.

**Company: GLEIF Accounting Direct Parent, with the reported ultimate parent.**
- Both ends are LEIs. The mapping, reader, cycle check and conflict check
  already exist (`source.yaml:149-162`; `relationships.py:152-206`).
- The file is already local. It is the Company gate item not yet started
  (`.scratch/company-mastering/remaining-work.md:110-111`).
- It is small for our Companies. Research found 53 records over 30 accepted
  children, and only 3 with both ends accepted. That count is dated
  2026-09-12 and was taken over an older Company scope
  (`.scratch/gleif-company-augmentation/research/04-parent-exception-summary.json`),
  so it must be measured again.
- Gaps: add the source to Company's list, and add a matching rule that joins
  the record's start LEI to its Company. Or change the engine so the start end is found from
  the LEI directly (fact 3).

**Correction to the ticket's plan.** Step 3 pairs Forms 3/4/5 with "accounting
parent and branch". Branch cannot come first. Branch is only a probable
kind, with no identity (`gleif/source.yaml`, `probable_kind_values`). Every
branch link would wait. Branch should wait for the Branch kind.

## What the relationship rules document must decide

- **Matching both ends.** For each type, the matching rule for each end
  (identifier or name). Deterministic ends act alone. A name end follows the
  same proof bar as identity rules (`person.yaml:326-330`). Say whether an
  edge with an unaccepted end waits as set aside, and when it is re-checked.
- **Identity of a relationship.** The key fields per type. For Person types
  this is decided: Person, Company and capacity. The engine's all-fields hash
  must change to it (`relationships.py:140-141`).
- **Intervals and dates.** A list of intervals per relationship. A date
  basis, stated or observed, on each date. The closers allowed per type:
  ADR 0008's four patterns plus the spec's three closers. Silence never
  closes.
- **Conflicts.** Overlapping accounting parents and cycles (already in the
  engine). An affirmative capacity dated after a stated end goes to a
  Steward, never silently reopened (`consumer.md:382-385`). Same-rank
  disagreement goes to the later event date.
- **Survivorship of dates and roles.** Stated beats observed
  (`consumer.md:376-378`). Title is a dated property, not identity. Profiles
  needed by a type, such as adviser, fund and audit firm, must be mapped
  before that type can publish.
- **Scope.** Which types are on, and which wait for a kind that does not
  exist yet (Branch, Fund Structure, Security issuer) as non-blocking
  `unsupported_relationship_type` (`skills/data-onboarding/REFERENCE.md:69`).
- **Approval and proof.** Each relationship rule is a versioned, digest-pinned
  rule in the Mastering Policy. It is proven by a Proving Run on a pinned
  cohort: counts of edges opened, closed, waiting and in conflict, and a
  hand-checked sample. It is switched on only by a named Rule Activation
  Approval (`CONTEXT.md:177-183`). Person feed 1 and the first relationship
  feeds switch on together (ticket 06, plan step 4).
