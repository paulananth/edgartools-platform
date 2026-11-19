# The complete Gold design (every approved final table)

Status: open
Type: task

The operator asked for the whole design, not one slice, made lean by the seven wastes and KISS. This replaces the 13F slice of
[ticket 02](02-gold-design-13f-slice.md) as the design of record; the slice's questions are folded in below. Method:
[GOLD.md](../../../skills/data-modeling/GOLD.md), [DIMENSIONAL.md](../../../skills/data-modeling/DIMENSIONAL.md),
[TEMPORAL.md](../../../skills/data-modeling/TEMPORAL.md). Inputs: `rules/exposure.yaml` (version
`exposure-2026-11-18.silver-mdm-and-published-rdm-codes`), all 16 registered silver tables, `mdm.mastering_master`,
`mdm.mastering_identifier`, `rdm.published_code`. Nothing here is built, approved or deployed.

## Parts

- [x] Read every silver spec (grain, links, time, measures, load mode) and the exposure list. 2026-11-19 09:26 ET
- [x] Write the whole bus, the object list, the cross-fact findings and the waste check below. 2026-11-19 09:26 ET
- [x] Operator answered the decision list: "Approved", 2026-11-19 09:30 ET, for all eight recommendations as written (section 7). Evidence: the design above and the 16 silver specs.
- [x] First requirement named by that approval: a manager's holdings by security and quarter. First build: `master`, `dim_company`, `dim_security`, `dim_date`, `thirteenf_filing` and `thirteenf_holding` facts (six views).
- [ ] Check what `DB_EDGARTOOLS_GOLD` holds today with a read-only identity (the operator's rule forbids the admin account and the `edgartools-prod` and `snowconn` connections: ask for a read-only connection)
- [ ] Write the Gold configuration for the six views (one file; grain, key, links, roles, members, requirement) and the shared dbt template that reads it; consult the GoF reviewer first
- [ ] Prove each view on the smallest sample (seven proofs, DIMENSIONAL.md) on an invented four-company fixture before any hosted run
- [ ] Build in the approved destination after the mirror exists and the load has finished
- [ ] Count, on the loaded stores, the rows each join would multiply or drop (needs the load)
- [ ] ~~dbt generator and views~~ deferred: no named requirement, no approved writable destination
- [ ] Learning → skill: gaps found when the first object is built return to `GOLD.md`

## 1. What Gold is for here (the context that sets the size)

- The approved final tables (16 silver, 2 MDM, 1 RDM) are mirrored into Snowflake and **can be read as they are**.
  AutoOntology and OpenMetadata read those tables directly (FINAL-TABLES.md). **They need no Gold.**
- Gold exists only where a consumption requirement needs a transformation the mirror cannot give. Three exist today:
  1. A master's fields sit in one JSON `body`, for every kind, with alias rows beside canonical ones. A typed query needs
     them unpacked.
  2. A certified Semantic View needs one Gold fact grain and Gold dimensions (semantic-views skill).
  3. A fact must join a dimension by the master id, with a defined answer for a key that did not resolve.
- No business question is approved yet. So the design is complete on paper and the **build list is empty** until one is named.

## 2. The objects: 23 views, 0 tables

Everything is a view over the mirror (waste: transport). Persist a view only after it is measured too slow.

| Kind | Object | Built from | Why one object |
|---|---|---|---|
| Base | `master` | `mastering_master` | Unpacks the structured body once: id, kind, canonical (not an alias), name, status. Every kind view and the relationship fact use it |
| Dimension | `dim_company`, `dim_security`, `dim_person`, `dim_fund` | `master`, one thin filter per kind, plus identifiers from `mastering_identifier` | One conformed dimension per kind, keyed by the master id; seven company roles are joins, not copies |
| Dimension | `dim_code` | `published_code` | One view of every published code, keyed by code set, version and code; a fact names the version it uses |
| Dimension | `dim_date` | generated | One calendar, joined twice as business time and recorded time |
| Fact | 16 views, one per silver grain | the silver mirror table | Grain taken unchanged from the silver spec |

Dimension attributes: only those a requirement names (default: name, identifiers, status). Each dimension has two
reserved members: **unknown** and **not applicable**.

## 3. The bus (all 16 facts)

Cells show the role. `C` = `dim_company`, `S` = `dim_security`, `P` = `dim_person`, `F` = `dim_fund`.

| Fact (silver table) | Grain | Type | C roles | S | P | F | Business time | Recorded time | Codes |
|---|---|---|---|---|---|---|---|---|---|
| `thirteenf_holding` | filing and holding | transaction | via filing: manager | held | | | via filing: report date | loaded | share type, option flag |
| `thirteenf_filing` | filing and manager | factless | manager | | | | report date | filing date | form |
| `nport_holding` | filing and holding id | transaction | registrant | held | | fund | period | filed | currency |
| `insider_position` | filing, table, line | transaction | issuer | | | | transaction date, as-of | filed | transaction code |
| `insider_reporting_owner` | filing and owner | factless | issuer, owner company | | owner person | | period of report | filed | |
| `company_fact` | filed fact | transaction | company | | | | period end | filed | concept, unit |
| `company_line_item` | company, line item, fiscal year | periodic snapshot (semi-additive) | company | | | | period end | filed | line item |
| `company_measure` | company, measure, fiscal year, window | periodic snapshot (semi-additive) | company | | | | fiscal year | loaded | measure |
| `adv_custody` | filing and custody row | transaction | adviser, custodian | | | | published | published | |
| `ipo_filing` | accession and CIK | factless | filer | | | | filing date | observed | |
| `registration_offering` | accession | transaction | registrant | listed | | | **not stated** | captured | |
| `registration_statement_line` | accession, table, row | transaction | registrant | | | | **not stated** | captured | |
| `prospectus_offering` | accession | transaction | registrant | listed | | | **not stated** | captured | |
| `prospectus_cover_line` | accession, table, row, line | transaction | registrant | | | | **not stated** | captured | |
| `prospectus_underwriter` | accession, table, row | transaction | registrant | | | | **not stated** | captured | |
| `relationship` | relationship and period start | factless bridge | both ends via `master` | both ends | both ends | both ends | valid from and to | loaded | relationship type |

Header and line facts (13F filing and holding; the two offerings and their lines; insider owner and position) stay
separate facts at their own grains and are never joined to each other (DIMENSIONAL.md, drilling across).

## 4. What the whole bus shows (a slice alone could not)

1. **`dim_company` carries seven roles** (manager, registrant, issuer, adviser, custodian, filer, owner company): one view, joined by role.
2. **`dim_security` is used by four facts** (13F holding, N-PORT holding, two offerings): a manager's holding and a fund's holding compare by drilling across on it.
3. **A 13F holding has no manager and no business date.** Both live on the filing, which has one row per accession *and manager*. Rule: reduce the filing to one row per accession first, or the holding multiplies; count it.
4. **Five registration and prospectus facts state no business time.** Silver holds only the capture time. A business-time column needs a profiling finding; until then these facts answer by recorded time only.
5. **An insider owner is a person or an organization.** Two links, one unused per row: the unused one is *not applicable*, not *unknown*.
6. **The relationship's ends are master ids of any kind.** They join `master`, not one kind view.
7. **Measures that must not be summed:** ratios and prices (`exchange_rate`, `percentage`, price per share, price low, high and fixed, conversion price), anything with a unit or currency column (N-PORT `balance`, company fact `value` by unit, 13F `shares_held` by share type), and every snapshot across periods.
8. **Repeating columns** (`value1` to `value4` with `year1` to `year4` on a statement line) are left as filed: pivoting them is a requirement's job (waste: over-production).
9. **No object needs history on a dimension.** Every question named so far uses the current master; type 2 waits for a named business date.

## 5. Waste and KISS check (every row must read "none")

| Waste | Check | Result |
|---|---|---|
| Over-production | Objects with no named requirement | All 23 are *planned*; none is built until a question names it |
| Transport | Copies of mirror rows | None: 23 views, no tables |
| Over-processing | Layers that only pass rows through | None: facts are views of silver, dimensions of masters |
| Motion | Per-fact or per-kind logic written twice | One `master` unpacking, one key template, one unknown-member rule |
| Inventory | Objects without a requirement | The design lists each object's requirement as it is named |
| Waiting | A build waiting on a decision the design could take | The design decides; the list below asks only what it cannot |
| Defects | Unchecked joins and units | Seven proofs per fact (DIMENSIONAL.md), row counts first |

KISS: no surrogate keys, no history dimension, no bridge except the relationship fact, no junk, outrigger, wide table or aggregate.

## 6. Decisions for the operator (one list, a recommendation each)

1. **The first named question.** Which business question justifies the first build? Recommended: a manager's holdings by security and quarter (it exercises `dim_company`, `dim_security`, `dim_date` and two facts).
2. **Destination.** The schema `GOLD` in `DB_EDGARTOOLS_GOLD`, written by a dbt role that reads only the mirror database. That database name held a control schema before: check it first.
3. **Views, not tables.** Approve the rule that an object is persisted only after a measured slow query.
4. **Dimension attributes** on `dim_company` and `dim_security`: name, identifiers and status only, until a requirement names more.
5. **Issuer of a security:** reached through the relationship fact, never copied onto `dim_security`.
6. **Business time for the five registration and prospectus facts:** ask profiling to find it, or accept recorded time only.
7. **13F amendments** are new accessions: keep them as rows; "latest amended position" only on a named requirement.
8. **`market_value` unit** across periods: profile it before any sum across quarters.

## 7. Approval record

Operator, 2026-11-19 09:30 ET: "Approved". Said in answer to the eight decisions in section 6, each with its recommendation. Approved in plain
words: (1) the first question is a manager's holdings by security and quarter; (2) Gold goes in schema `GOLD` of
`DB_EDGARTOOLS_GOLD`, written by a dbt role that reads only the mirror database, after the existing contents are checked;
(3) a Gold object is a view, persisted only after a measured slow query; (4) dimensions hold name, identifiers and status only;
(5) a security's issuer is reached through the relationship fact; (6) profiling looks for a business time of the five
registration and prospectus facts, otherwise they answer by recorded time; (7) amendments stay rows; (8) `market_value` is
profiled before any sum across quarters. It changes no store, role or Snowflake object: it approves the design and the
destination name only. Building waits for the mirror and the finished load.
