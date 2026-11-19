# Dimensional modeling toolkit

Read this when a Gold design needs a technique beyond the one-grain, one-dimension-per-kind rules of
[GOLD.md](GOLD.md): which fact type, whether a measure adds, which dimension technique, how history is kept, how late
or missing keys behave, or whether a design is sound. The techniques are the Kimball Group's published list; each row
says what it means on this platform, where masters (MDM), code sets (RDM) and silver already hold the integrated data
and Gold is the consumption shape. This file proposes a shape. It does not write dbt, approve an exposure list or
approve a destination.

## The four steps, as this platform does them

| Kimball step | Here | Evidence it is done |
|---|---|---|
| Choose the business process | One registered silver transaction part, or one dated relationship | The silver table named, with its requirement |
| Declare the grain | The silver spec's `grain:` sentence, unchanged | One sentence a reader can count from |
| Identify the dimensions | The spec's `links` (each `mdm_id_column`), its time roles and any code it states | Each dimension named once, each join a role |
| Identify the facts | The spec's measure columns, each with its unit | Each measure with its additivity (below) |

Declare the grain before anything else; a dimension or measure that does not fit the grain is a different fact.

## The bus matrix

The planning artifact is a grid: one row per fact, one column per conformed dimension, a mark where the fact joins it,
and the role beside the mark. It lives in the design record of the build, and it is how conformance is checked: a
dimension used by two facts must be the same view with the same attribute definitions in both.

**Completion:** every fact on the bus, every dimension column one view, and each empty cell either a deliberate absence
or a question for the operator.

## Fact table types

| Type | Row is | Use here when | Watch |
|---|---|---|---|
| Transaction | One discrete event | The silver row is an immutable report (the default for an append table) | Corrections are new rows; the fact stays append |
| Periodic snapshot | One subject, one regular period | Silver rebuilds a period (fiscal year, quarter) | Semi-additive across periods |
| Accumulating snapshot | One process, milestone dates fill in | A requirement names the milestones | Updates in place: needs a rebuild rule |
| Factless | One occurrence or one link, no amount | A report exists; a relationship was in force | Counting is the measure |
| Header and line | Two facts at two grains | A report and its lines both carry measures | Allocating a header amount to lines is an allocation rule the operator approves |
| Aggregate | A rollup of one fact | Only after measured slowness of the base fact | Never the model of record; rebuilt from the base fact |
| Consolidated | Two processes at a common grain | Only when a requirement compares them and their grains truly match | Mixing two grains in one table is the usual error; keep two facts and drill across |

A derived measure that needs a lag (days between two dates) is a lag fact computed from two date roles; keep both dates.

## Additivity: declare it for every measure

| Kind | Rule | Examples of the shape |
|---|---|---|
| Additive | Sums across every dimension | A reported amount of a transaction |
| Semi-additive | Sums across subjects at one period, never across periods | A balance, a period-end position, a fiscal-year line item |
| Non-additive | Never summed | A ratio, a rate, a price |

Store a ratio's numerator and denominator as additive measures and divide after summing; a stored ratio cannot be
re-aggregated. A measure with a unit or a currency column adds only within one unit (GOLD.md): carry the unit beside the
amount, and where the requirement needs one unit, store the converted amount beside the reported one with the rate's
source named. A year-to-date measure is a query over the period fact, not a stored column.

## Dimension techniques

| Technique | Use here when | Rule |
|---|---|---|
| Conformed | Two facts link to the same kind | One view, one key (the master id), one definition of each attribute |
| Role-playing | One kind appears twice in a fact (holder and issuer, two dates) | A second join to the same view, aliased by role; never a copy |
| Degenerate | A report key with no attributes (a report number, a line number) | Stays on the fact |
| Junk | Several low-cardinality flags no kind owns | One small dimension of the combinations that occur, only after the flags are counted; else leave them on the fact |
| Outrigger | An attribute set that belongs to another kind (a security's issuer) | Join the second conformed dimension through the master relationship; do not copy its attributes into the first |
| Mini-dimension | Attributes of one kind that change fast and are queried as a group | Only on a named requirement; the fact then holds both keys |
| Multivalued with a bridge | A fact row has several values of a dimension (a report naming several owners, a security with several identifiers) | A bridge at its own grain with a weight only if the requirement allocates; joining it multiplies the fact, so count |
| Hierarchy | A parent chain (corporate parent, a code set's tree) | Fixed depth: columns on the dimension. Ragged: the relationship bridge, never a recursive column |
| Snowflaked | Normalising one dimension into several tables | Not by default; a star is easier to query and to certify |
| Calendar | Business time and recorded time | One date dimension, two roles; the fiscal calendar is an attribute set, never a second dimension per source |
| Audit | A fact needs its lineage | Columns on the fact: source table, mapping or rules version, mirror time, build id; never a join to a log |

## Keys

- **A master's key is the MDM id.** It is the durable key: it survives a merge (the alias row names the survivor) and
  never comes from a source. A dimension needs no second surrogate unless it keeps history, and then the key is the
  master id plus the version's valid-from.
- **A source key is a lookup, never a join.** The silver link already filled the master id; a Gold model that joins on a
  source identifier has bypassed mastering.
- **A fact's key is its grain's natural key** (the silver `key:`). Add a fact surrogate only where a downstream consumer
  needs one row identity, derived by one shared deterministic macro, and say who needs it.
- **Never a business meaning in a key.** An identifier keeps its leading zeros and is stored as filed.

## Slowly changing dimensions

| Type | Meaning | Here |
|---|---|---|
| 0 Retain original | Never changes | An identifier as first issued; a first-seen date |
| 1 Overwrite | History lost | **The default.** The dimension is the current master; MDM keeps the history |
| 2 New row | Effective-dated rows | Only when a requirement names a business date at which the attribute must be the one then true; built from master versions, never from Gold's own diff |
| 3 Prior-value column | One step of history | Only for a named "before and after" requirement on one attribute |
| 4 Mini-dimension | Fast-changing attributes apart | See the table above |
| 5 to 7 | Hybrids of 1, 2 and 4 | Only when one question needs both the historical and the current value; type 7 (the fact holds the master id and the version key) is the one to try first |

A type 2 dimension is a larger join and a larger risk of multiplied rows: join on the master id and the fact's
business date falling inside one version's validity, and prove one version per fact row.

## Missing, early and late keys

| Case | Rule |
|---|---|
| A fact's link found no master | The dimension's **unknown member**; the fact key is never null; report the count |
| A fact's attribute is null | The measure stays null, never zero; a null is not "no amount" |
| A dimension attribute is null | Stays null in the data; a display label such as "not stated" is the semantic layer's job, so no value in the data is invented |
| The master arrives after the fact | Gold is rebuilt from the approved mirror, so a later rebuild re-keys the row once silver's ids are refreshed; no placeholder is updated in place |
| A reported value arrives for an earlier period | Business time stays the period it describes; recorded time is when we learned it |
| Two business times on one row | Two date roles, each a join; never one column that means either |

## Drilling across

Two facts are never joined to each other. Aggregate each to the grain of the shared conformed dimensions, then combine
the two results by those dimensions. A measure that appears in two facts is conformed: one definition, one unit. A
question that needs two facts at different grains is two queries and a join of their aggregates; a semantic view over
one fact ([semantic-views](../semantic-views/SKILL.md)) does not do this for you.

## Proving a Gold model

Each is a dbt test, a unit test with an exact expected result, or a reconciliation count, and each is reported apart from
mirror replication and access:

1. The fact's key is unique and not null (the grain holds).
2. Every dimension key resolves (a relationships test), the unknown member included; the unknown count is reported.
3. A join to each dimension leaves the row count unchanged; a type 2 or bridge join is counted explicitly.
4. The fact's row count equals its silver table's, or the difference is named (a declared filter).
5. Each additive measure's total equals silver's total for the same scope; a decimal is compared exactly.
6. One invented record per rule in a small test proves the unit, the role and the unknown-member behaviour.
7. A dimension has one row per master id in scope (type 1) and none for an alias of another record.

## Snowflake and dbt practice

- **Constraints are declared, not enforced.** A standard Snowflake table does not enforce unique, primary-key or
  foreign-key constraints. Declared with `RELY`, they let the optimizer drop a join it need not run: a left outer join
  whose right key is unique or primary, or an inner join between a primary key and a foreign key, when the query reads
  no other column of the dropped table. If the data breaks the constraint, results differ from the same query without
  `RELY`. So **set `RELY` only on keys whose uniqueness and relationships tests (Proving, above) pass**, and keep the
  unknown member so every foreign key resolves.
- **Clustering is for very large, read-mostly tables.** Snowflake's guidance: consider a key only on a table of many
  terabytes, with selective filters or sorts on a few of the same columns, little DML, and when the speed-up outweighs
  the credits to keep it clustered. At most three or four columns, filter columns first (a date), neither booleans nor
  nanosecond timestamps (cast a timestamp to a date), lowest cardinality first. A dimension, or a fact that has not
  measured slow, is not clustered.
- **dbt's dimensional build.** Process, grain, dimensions, fact; dimensions as tables or views, facts as tables and
  incremental once they reach millions of rows; a unique and a not-null test on each key; an entity-relationship
  diagram for consumers. The published guide hashes natural keys into surrogate keys so a fact computes its foreign keys
  without joining the dimension; here a dimension's key is the master id, so the fact already holds it. The guide does
  not cover snapshots or type 2 history, and treats a wide table as the fallback when a reporting tool cannot read
  relationships.
- **Late-arriving facts.** Kimball's rule: look up the dimension key that was in effect when the event happened, not the
  current one. It matters only for a type 2 dimension; for type 1 the current master is the answer.

## Smells and their fix

| Smell | Meaning | Fix |
|---|---|---|
| More than about fifteen dimension keys on a fact | A centipede | Merge the junk, or split by process |
| A fact joined to another fact | The grains differ | Drill across |
| A measure summed across a unit or period it should not | Missing additivity | Declare it, group by the unit |
| One table holds two grains | A consolidated fact that is not | Two facts |
| A dimension copy per source or per role | Not conformed | One view, role joins |
| A stored ratio, average or percentage | Non-additive | Store the parts |
| Every dimension type 2 | History nobody asked for | Type 1, history stays in MDM |
| A Gold table nobody's requirement names | Speculative | Do not build it |
| A wide table as the only model | No bus | The star first, the wide table a mart of it |
| Text in the fact | Comment or label | A dimension or the semantic layer |

## Hand off

The decision is the handoff, as in GOLD.md: the design (bus matrix, grain sentences, dimension roles, additivity per
measure, history type per dimension) goes to the operator; dbt and the target are
[aws-snowflake-operations](../aws-snowflake-operations/SKILL.md); a certified question is
[semantic-views](../semantic-views/SKILL.md).

## Examples

The registered silver grains as a bus (examples only; the shapes above do not depend on them). Rows are facts, columns
the conformed dimensions, a cell the role.

| Fact | Company | Security | Person | Date (business / recorded) | Code sets |
|---|---|---|---|---|---|
| A fund manager's reported holding | manager | held | | report period / filing date | share type, option flag |
| A fund's reported holding | registrant | held | | report period / filing date | |
| An insider's reported line | issuer | issued | owner (bridge: joint filings) | transaction / filing date | line table |
| A filed company fact | filer | | | period end / filing date | concept, unit |
| A fiscal-year line item | company | | | fiscal year (semi-additive) | line item |
| A relationship in force | both ends | | | start, end | relationship type |

Two facts that share Company and Security (a manager's holding and a fund's holding) are compared by drilling across,
never by one table holding both grains.
