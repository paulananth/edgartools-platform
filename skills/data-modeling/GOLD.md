# Gold warehouse

Read this when the question is how approved final tables become a
business-facing warehouse: the technique, one fact grain, the conformed
dimensions, and the time scope. The class, kind, identifier, code set,
relationship and silver decisions stay in [SKILL.md](SKILL.md). This file
does not write a dbt model, deploy a database, or approve an exposure list.

Approved mirror tables can be queried directly without dbt or a Gold build.
Use Gold when a consumption requirement needs a modeled transformation;
the mastered identity stays in MDM.
A Gold fact is the consumption shape of a transaction part or a relationship
that silver already holds, plus dimensions from the masters and code sets.
It is not a new data class, and it is not an exposure source.
[Final exposable tables](../data-platform/FINAL-TABLES.md) lists final master,
reference and silver tables. For required Gold transformations, dbt reads that
approved mirror and writes Gold. The database and schema names are undecided;
record and obtain approval of the exact writable destination before a build.
An existing database, example name or control-schema location is not target
approval. Execution follows
[aws-snowflake-operations](../aws-snowflake-operations/SKILL.md). A question
contract on one built fact is
[semantic-views](../semantic-views/SKILL.md).

## Choose the technique

First state the consumption requirement and whether direct reads of the
approved mirror satisfy it. If they do, stop at consumer access qualification;
do not build a duplicate table or require dbt just to serve the same rows.
The Gold modeling method below applies when transformations are needed.

## dbt implementation requirements

- Apply this method to any business domain. Resolve the entity and fact list
  from approved modeling configuration; no fixed entity names or three-entity
  limit controls the build. Each entry declares its approved input assignments,
  output view identity, key, attributes, relationships and current/history scope.
  Fact entries also declare their grain, measures and dimension joins. Keep
  connections and credentials outside these model definitions.
- Gold has dimension and fact models. Expose each configured mastered entity as its own
  dimension view, using dbt's `view` materialization; do not combine distinct
  entities into a single dimension. Facts have their own business grain and
  refer to those shared dimensions through master keys. A separate fact is
  not required merely because an entity has a dimension view.
- Reuse a conformed dimension across domains when it represents the same
  modeled entity. A new domain or a different join role does not create a
  second copy. RDM code-set dimensions retain their approved version; date
  dimensions retain their declared business-time or recorded-time role.
- An entity dimension view is an ordinary SQL view, not a Snowflake Semantic
  View. A Semantic View is the separately certified question contract over
  one Gold fact grain and its dimensions; apply
  [semantic-views](../semantic-views/SKILL.md) for that later stage. A dimension
  view alone does not certify questions or authorize another consumer source.
- Use a shared model-generation path or reusable dbt templates/macros driven by
  those entries. Adding a domain or entity changes configuration and its grain,
  key and join tests, not a copied domain-specific implementation. Verify the
  installed project's actual capabilities before using this path; this skill
  defines requirements and does not claim a generator or models already exist.
- Link each model to the consumption requirement and its approved input-table
  assignments. Mirroring and direct reads do not depend on dbt readiness.
- Record the approved output database and schema, materialization, execution
  role and warehouse in deployment configuration; do not supply a production
  destination by convention or copy one from an example.
- Use dbt for Snowflake transformation writes. Its role reads only approved
  mirror inputs and writes only to the approved writable destination, outside
  the read-only mirror database. Reader access remains separately controlled.
- Declare approved mirror inputs as dbt sources and prove grain, key uniqueness,
  nullability, exact-number calculations and join multiplicity for the required
  model. Report Gold acceptance separately from mirror replication and access.
- Provisioning Postgres ingress does not create Gold models or a Gold schema.
  A Gold name previously used for an operational object remains unapproved as
  a model destination until explicitly reviewed.

## Model the required Gold output

The integrated store already exists. MDM holds identity and master attributes,
RDM holds code sets as versions, silver holds each transaction grain, and the
relationships hold each dated link. Gold is the mart on top of the approved
mirror of that store.

| Technique | Shape | On this platform |
|---|---|---|
| Conformed dimensional bus (Kimball) | One fact per grain. Dimensions shared across facts. | The Gold model of record. A semantic view is already one fact grain, its dimensions, and joins that preserve that grain. |
| Corporate information factory (Inmon) | A normalized integrated core, then dependent marts. | The core is MDM, RDM and silver. The mirror is its read-only copy. Gold is the mart layer. |
| Data Vault | Hubs for business keys, links for relationships, satellites for described history. | Identity, the cross-reference, relationships and silver values already play those parts. A vault in Gold would master a second time. |
| Anchor modeling | One table per attribute, with its own history (sixth normal form). | Attribute history already lives on master versions and code-set versions. |
| Activity schema | One stream of timestamp, entity and activity. | A published mart of one fact's events, after that fact exists, and only when the requirement asks for a stream. |
| Wide table | One denormalized table per question. | A published mart of one star, after that star exists. The star stays the model of record. |

### What the sources establish, and their limits

Read from the techniques' own published material; a claim a source does not make is marked.

- **Conformed bus against a normalized core (Kimball, Inmon).** The Inmon
  wording of a data warehouse (subject-oriented, integrated, time-variant, nonvolatile) and of the dependent mart is from
  secondary descriptions only: his books were not reachable, so quote nothing from him as his. The bus integrates dimensional marts through shared
  conformed dimensions with no central normalized store; the Inmon design keeps a normalized enterprise store and
  builds dependent marts from it. The bus is delivered faster and in increments but needs strict governance of
  dimension definitions, or the marts fragment into silos; the normalized core is simpler to load and harder to query.
  One published survey of practitioners found no clear winner, independent marts the worst, and the hub-and-spoke build
  the slowest to deliver. On this platform the normalized core already exists (MDM, RDM, silver), so Gold takes the bus.
- **Data Vault.** A hub is a unique list of source-agnostic business keys (never a source system's surrogate id) with a
  hash key, a load time and the record source that first supplied it. A link is an intersection of at least two hubs,
  many-to-many by design so a cardinality change needs no redesign. A satellite holds descriptive attributes and their
  history, keyed by the parent hub or link and a load time, with a hash of all its descriptive columns so change
  detection is one comparison; it only ever inserts. The raw vault loads source data exactly as it arrived, with no
  cleansing or business rules ("a source of facts, not of truth"); business rules and cleansing come downstream in a
  business vault or information marts, usually dimensional. Stated limits: hubs carry no foreign keys, the business keys
  must be right, and the hash comparison can be overkill for a small table. The Data Vault Alliance and Linstedt's own
  specification were not reachable: these points are from practitioner and vendor descriptions, and no official
  Snowflake source prescribes a hub-to-mart pattern. A vault here would master and historize a second time, and the
  platform already keeps the source's own values, key and record source in silver and the Cross-reference.
- **Anchor modeling.** An anchor holds only the identity of a thing that persists while its properties change; an
  attribute is one property in its own table (static, or historized with a start time); a knot is a small shared closed
  list of values; a tie is a relationship between two or more anchors, one role each; a nexus is an event-like entity
  with its own identity, properties and roles. Each property and relationship gets its own table (sixth normal form),
  except a tie or nexus with several non-identifier roles, kept whole. History is only added, never updated in place,
  and only where needed; a historized tie cannot delete an ended relationship, so the end becomes a new state. The
  generator emits views over the narrow tables (latest, point-in-time, difference, now); the latest view is the usual
  query surface. Stated benefits: extension adds tables, so old queries keep working; no nulls; narrow reads. Limits: many
  narrow tables that depend on the views and join elimination to reassemble; closed intervals add query complexity;
  target support varies and some generators were never run on a live server; it is called an advanced technique, and the
  page comparing it with a vault comes from one of its creators. Its author's published practice (history, as-of joins, identity, layers) is in [TEMPORAL.md](TEMPORAL.md). Here
  attribute history already lives on master and code-set versions, so the model would historize a second time.
- **Activity schema.** One time-ordered stream per entity type: an activity id, a UTC timestamp, the entity's global
  identifier (or an anonymous one until resolved), the activity name, a semi-structured feature object with the same
  keys for every row of one activity, an optional revenue amount and a link to the source record. Activities join to
  each other on entity and time, never by foreign key (first, last, before, after or between a cohort row). Limits it
  states: activities are immutable, so a changing status is a new activity; one identifier type per entity; only
  top-level features are read; dimension data is joined at query time; performance tuning is left to the warehouse.
  It suits one fact's events after that fact exists, not the model of record.
- **Wide table (one big table).** A fallback consumption shape when a reporting tool cannot declare relationships:
  the fact joined to every dimension. It is a mart of the star, never the model.

**Completion:** name the conformed dimensional bus, or name another row and
the requirement that asks for it. A wide table or an activity stream is a
mart of a fact that is already on the bus.

## Design the whole bus first, then build the least

A fact designed alone cannot be conformed. Before any one Gold object is built, write **one design for every approved
final table**: the bus matrix (DIMENSIONAL.md), each fact's grain, the dimension set, the roles each dimension plays, the
missing-key members, and what is deliberately not built. A later slice cites that design and changes it only by changing
the whole. The design is cheap (a document); the build is not, so the two are kept apart.

**Lean by the seven wastes** ([data-platform](../data-platform/SKILL.md#the-seven-wastes)) **and KISS.** Apply them to every
Gold object, in this order; an object that fails one is dropped or deferred, not built and tuned.

| Waste | In a Gold design | Rule |
|---|---|---|
| Over-production | A table, column, dimension or aggregate no question needs | **Every object names the requirement that needs it.** An approved silver table spec is the requirement of its own fact: every exposed silver table gets its fact view, made from the spec. A further object (a snapshot, an aggregate, a wide table) names its own requirement, and with none it stays on the bus as "planned" |
| Transport | A copy of mirror rows in Gold | **A Gold fact or dimension is a view over the mirror by default.** Persist only a view measured too slow, naming the time and the cost |
| Over-processing | A rebuild, a proof or a layer after the input is proved | Prove once on the smallest sample that holds each case; carry the proof forward while input and rules are unchanged; no layer that only passes rows through |
| Motion | Writing the same logic per source or per fact | Dimension unpacking, the unknown members and each fact's key checks are one shared template driven by configuration |
| Inventory | Objects whose requirement ended | Each object lists its requirement; an object with none left is removed in the same change |
| Waiting | Questions a ruling already answers; a build held for a decision the design could take | Decide what follows from a ruling; ask the remaining decisions as one list with a recommendation each |
| Defects | A join that multiplies rows, a unit summed wrongly, a key that does not resolve | Run the proofs (DIMENSIONAL.md) on bounds first: row counts before and after each join |

**No silver table is silver-only.** A silver table is approved for a use when its spec is approved, so Gold carries it: the
fact view is made from the spec, never written by hand. The spec's `key` is the fact's key; each of its `links` becomes a
`<to_part>_key` column joined to the dimension of the link's `kind` (the unknown member when no master holds the id); its
`time.as_of` is the business date, `time.event_time` the event date and `time.as_at` the recorded date; every other spec column is carried as filed. A fact
the spec alone cannot make (a date or a manager taken from a parent table) is written as its own object in the
configuration, and the spec's generated fact gives way to it. Each dimension a link names is configured. The mirror then
carries what these views read ([HOSTED-MIRRORING](../data-platform/HOSTED-MIRRORING.md)).

**KISS in shapes:** the fewest objects that answer the questions. One fact view per silver grain; one base view of the
masters with a thin view per kind on it; one view of the published codes; one date dimension. No surrogate keys (the
master id is the key), no history dimension until a named business date needs it, no bridge until its rows are counted
and a question needs it, no junk or outrigger dimension, no wide table, no aggregate, no snapshot copy. A new object is a
decision recorded against a requirement, never a default.

**Two kinds of absent dimension key** are two members: *unknown* (the lookup failed, a mastering finding) and *not
applicable* (the role does not apply to this row, such as a person owner on a row whose owner is an organization).
Never one member for both.

**A relationship joins masters of any kind.** Its two ends are master ids, not one kind, so it joins a base view of
all masters (id, kind, canonical, name, status) and each kind view is a thin filter on that base: the unpacking of the
master's structured body is written once.

## One grain

1. **Write the grain in one sentence** ("one row per …"). A reader can count
   the rows from the sentence. Two sentences are two facts that share
   dimensions.
2. **Take the grain from the silver spec** (`grain:` on the registered
   table). Gold does not invent a finer key, and it does not drop a part of
   the key the spec uses to tell rows apart.
3. **Classify that grain:**

   | The silver row is… | The fact is a… | Additivity |
   |---|---|---|
   | one immutable event, append-only; a later correction is a new row | transaction fact | amounts add across the fact |
   | one subject at one regular period, rebuilt to that period | periodic snapshot | amounts add across subjects at one period, not across periods |
   | one process whose milestone dates fill in as it advances | accumulating snapshot | the requirement names the milestones |
   | one dated link between masters, with no amount | factless fact, used as a bridge | the question is whether the link was in force |

4. **A derived snapshot stays its own fact.** When silver rebuilds a
   periodic snapshot from an event table, Gold keeps both: the event fact
   holds every reported row, and the snapshot fact holds the rebuilt grain.
   The definitions of those derived rows stay in the skill that owns them.
5. **A relationship is a bridge at its own grain** (one row per link and
   period). Copying one end's attributes onto another fact answers a
   different question and changes that fact's grain. Put the bridge on the
   bus and join it in the question that asks about the link.
6. **Prove the grain before a build.** Count the rows the key would drop or
   multiply (section 8 and section 9 of the skill). A join that increases
   the row count has changed the grain: include the extra key in the
   sentence, or keep the two grains as two facts. A report key with no
   attributes of its own stays on the fact (a degenerate dimension).

**Completion:** one sentence, one fact type from the table, and the count of
rows the key would drop or multiply (zero, or the operator decides).

## Dimensions, types and time

- **One conformed dimension per master kind**, keyed by the master id. Every
  fact that links to that kind uses that dimension. A role (holder, issuer,
  custodian) is a second join to the same dimension view, not a second copy of
  it. Expose each kind as a separate Gold view over approved mirror inputs;
  the view is a consumer projection and does not master the entity again.
- **A key no master has joins an unknown member.** A fact whose silver link found no master keeps its source key, and in
  Gold its dimension key is the dimension's one "unknown" member, never null and never dropped. The build reports
  the count of rows on it; a rise is a finding about mastering, not a Gold fix.
- **A measure with a unit column adds only within one unit.** Where the row's unit changes the meaning of the amount
  (shares against a principal amount), or a flag marks a derivative of the subject (an option on a security), a sum
  across them is wrong: the question groups by the unit, or the fact carries one measure column per unit.
- **A fact takes a date from a sibling silver table only through that table's whole key.** If the sibling has
  several rows per the join key (a record listed by two parties), reduce it to one row per the fact's key first, and
  count the rows before and after.
- **A dimension view unpacks the master's declared fields.** The master keeps its fields in one structured body for
  every kind; the view filters one kind, drops rows that are aliases of another record, and takes its typed columns
  from the kind's declared fields, so a new field is a declaration.
- **The fact holds its own measures and the master-id links.** Master
  attributes stay on the dimension. The row's own unit stays beside the
  amount it measures (one system of record, in the skill).
- **A code set is a dimension that names its approved version.** A new
  version is a new row of that dimension, not a rewritten label.
- **Two times stay apart**, as in the skill: business time (when it was
  true) and recorded time (when the platform knew it). Each is its own join
  to one date dimension. The fact declares which columns carry which.
- **The current master is the dimension.** A dimension row per historical
  version (slowly changing type 2) is built only when the requirement names
  a business date at which the attribute must be the one then true. The
  history itself stays in MDM; Gold reads it.
- **Time scope is the scope already decided for the exposure entry**
  (current, or approved history). The Gold table declares that same scope.
  A table with no declared scope is not a semantic-view source.
- **Integers are `BIGINT`. Decimals are exact `NUMBER(precision, scale)`**,
  with precision and scale taken from the profiled maximum and room for a
  wider value. A float is not a Gold type.
- **Every input is on the approved exposure list**, with its role and
  version. A table still proposed is named as proposed. The build waits
  until that list is approved. This skill proposes the Gold shape and does
  not approve the list.

**Completion:** each dimension named once, each role a join, business time
and recorded time assigned to columns, time scope declared, and each input
marked approved or proposed.

## What to write down

- Technique, and the requirement when it is not the bus.
- Grain sentence and fact type.
- Dimensions, and each join's role.
- Measures that belong to the row, and the master attributes left on the dimension.
- Business-time columns, recorded-time columns, and the declared time scope.
- Inputs, each approved or proposed.
- Whether direct mirror reads suffice; otherwise the required transformation
  and the approved writable destination, or an explicit pending naming decision.
- The row count the key would drop or multiply.

## More techniques

[TEMPORAL.md](TEMPORAL.md) holds history, as-of joins, corrections and identity. [DIMENSIONAL.md](DIMENSIONAL.md) holds the rest of the toolkit: the bus matrix, fact and dimension types, additivity,
slowly changing history, late and missing keys, drilling across, and the proofs a Gold model needs.

## Hand off

The decision is the handoff. dbt implementation and the warehouse target are
[aws-snowflake-operations](../aws-snowflake-operations/SKILL.md). A certified
question on one of those facts is
[semantic-views](../semantic-views/SKILL.md): one fact, joins that preserve
its grain, no silver query. A missing exposure approval stops the build and
returns to [Final exposable tables](../data-platform/FINAL-TABLES.md).

## Examples

For one configured domain, Person, Company and Security each have a separate
Gold dimension view. Another domain supplies its own approved entity list to
the same modeling method. Facts join dimension views through their respective
master ids at the fact's declared grain. These entity labels do not approve
physical view, schema or database names, and this document does not claim the
views have been deployed.

Examples only. These are the registered silver grains read as a bus. They
are not installed dbt models. Nothing above depends on them.

The shared dimensions are Company, Person, Security, the date (business and
recorded as two roles), and the code sets a fact actually uses
(`financial-line-items`, `mdm-relationship-types`, and a measure's own code
when the measure list is a code set). A fact joins a dimension through the
master id its silver link declares (`mdm_id_column`). The source key stays
the lookup that fills that id.

| Silver grain | Fact on the bus | Why it is its own fact |
|---|---|---|
| `company_fact`: one row per filed fact (company, taxonomy, concept, unit, period, filing). `rules/sources/sec.company-facts/silver-company-fact.yaml` | Transaction fact. Every filed copy stays. | The event grain. Line items and measures are built from it and do not replace it. |
| `company_line_item`: one row per company, line item and fiscal year. | Periodic snapshot. | Latest-filed standard line item. A different grain from the filed fact, and a different grain from a registration page's stated lines. Definitions stay in the company-financials skill. |
| `company_measure`: one row per company, measure, fiscal year and window. | Periodic snapshot. | A measure over the line items, including a multi-year window. Semi-additive: one period at a time. |
| `relationship`: one row per relationship and period start. Rebuilt (`load_mode: snapshot`). `rules/silver/silver-relationship.yaml` | Factless bridge. | The link and its period. Parent, adviser or issuer attributes stay on the masters. A holding fact does not grow a parent column. |
| `thirteenf_holding`: one row per accession and holding index. Append. Manager, report period and filing date live on `thirteenf_filing` (one row per accession and manager, also append). | Transaction fact of a reported position. An amendment is a new accession, so two filings of one quarter stay two rows. | A periodic snapshot (one row per manager, instrument and report date) is a further fact, and only when a requirement says which amendment wins. Join to the filing on the key that keeps one filing row per holding. The filing grain includes the manager, so an accession shared by two managers multiplies holdings when the join is the accession alone. CUSIP stays the link key; the class title and the FIGI stay on the Security dimension through `security_mdm_id`. |
| `nport_holding`: one row per accession and holding id. Append. | Transaction fact of its own. | A fund holding (series, registrant, Security). The value currency stays on the row. A manager's 13F position is a different grain and a different question; the two facts share the Security dimension and are not stacked into one table. |
| `insider_position`: one row per accession, table and line. Append. `line_table` is transaction or holding, derivative or not. | Two transaction facts when both questions exist: the trade lines, and the lines that state a position. | Both are filed rows. Collapsing the position lines to one row per holder and date is a further snapshot, with the same amendment rule as a 13F position. The Security link is not on the row: the form names a class in words. |
| `insider_reporting_owner`: one row per accession and reporting owner. | Factless fact at the owner grain. | A joint filing names each owner once and the lines once. Joining owners to lines on the accession multiplies the lines. Keep the two facts until a source pairs a line to an owner. |
| `adv_custody`: one row per filing and custody row. | Transaction fact of the reported amount. | The amount is the row's own measure. Adviser and custodian attributes stay on the Company dimension through the two master ids. The latest filing is a query over this fact, or a later snapshot, not a second copy of the amount. |
| `registration_offering`: one row per accession. | Transaction fact of the cover terms stated on that report. | An accumulating snapshot waits until a requirement names the milestones of the offering. |
| `registration_statement_line`: one row per accession, table and row. | Transaction fact of the figures that page states. | Not `company_line_item`. One is a page in a registration report; the other is a fiscal-year line item rebuilt from filed facts. |

A type 2 Company dimension is the current Company until a requirement asks
for the name as of a past business date. Aliases and non-surviving values
already live on the Company master.

A wide table that places `company_measure` beside `thirteenf_holding`, or an
activity stream that appends both, mixes a fiscal-year snapshot with a
holding event. Each stays a fact. A semantic view then takes one of them.
