---
name: data-profiling
description: Profile ANY data set and record the silver fields it needs - every number, every identifier, and commentary text only when that text is material - plus the part's class, keys, links, code lists and time roles. Writes REPORT.md and findings.yaml. Use before onboarding a new data set (data-onboarding calls it), or to compare a new delivery with approved findings (refining-rules calls compare).
---

# Data Profiling

Work lean: check each step against [the seven wastes](../data-platform/SKILL.md#the-seven-wastes) and drop what adds no value.

> Part of the **data-platform** skill set. This skill only reads data and
> writes findings. It never changes a store, a rule or a source.

Given a data set, it records **what silver needs from each part**: every
numerical column and every identifying column (keys, codes, links, dates and
names), and commentary text only when that text is material. It also says how
the parts connect. The store suggestion is advice only.

## Silver fields

Operator. This is the rule the silver spec follows.

- A number is a silver field when it is filled on any row. The column profile
  records its minimum, maximum, how many values are zero, how many are
  negative, and, for a decimal or fraction, the most decimal places seen.
  Cardinality (`unique`, distinct divided by filled rows) near 1 is an
  identifier; near 0 is a category or a repeated measure.
- An identifier is a silver field: the record key, a code, a link, a date, or
  a name. A check digit and a second unique shape are recorded on
  `identifiers`, as data-onboarding's identifier types already expect.
- Commentary is text that is not an identifier. It is a silver field only when
  it is material: filled on at least half the rows, at least two values, and
  the most common value is under nine tenths of the filled rows. A constant
  sentence, an empty column, or a rare note stays in the column profile and
  stays out of the silver spec.
- When the five class tests do not pick one class, the part's class is
  `silver`. The tests stay in the findings. The run still writes the silver
  fields. It does not stop to ask which class the part is.

## Every date, number and identifier has one written shape

Standing rule (operator, after a date written `DD-MON-YYYY` was read
into two different shapes by two mappings: "this should be a standing rule on
the data profiling skill"), worked adaptively and lean against
[the seven wastes](../data-platform/SKILL.md#the-seven-wastes)
(operator: "use adaptive profiling and be intelligent").

- **Start from what the profile already holds** (Motion, Over-processing). The
  column profile records each field's shape counts; read them before touching
  the files again. A field with one shape on every filled row is done.
- **Widen only where the sample says so, and stop when it converges.** A
  seeded sample first; read a field in full only when the sample shows two
  shapes, a shape the mapping does not parse, or rows that fit none. One more
  pass that adds no new shape ends that field.
- **Check only the fields that feed a silver field, a key, a link or a
  matching rule** (Over-production). Commentary and fields no step reads are
  left alone.
- **One answer per input field** (Inventory). Two mappings reading the same
  input field share the result: profile the field once, and a test feeds both
  mappings the same record and compares what they give.
- **Report counts, never a value from the data:** the shapes seen, each
  one's count, and the rows that fit none.
- **Fix in the mapping:** one declared shape per field, converted once, to the
  same calendar form wherever sources share a kind (a date is `YYYY-MM-DD`). A
  row that fits none becomes none and is counted, never guessed.
- A profiled number is typed `BIGINT` (integer), or exact `BIGDECIMAL` in code and
  `NUMBER(precision, scale)` in a database (decimal), never a float; the profile
  records the digits and decimal places that set the precision and scale.
- **Carry the result forward** (Waiting, Defects): the shapes go in
  `findings.yaml`; `compare` reports a field whose shape counts moved, and only that field is checked again.

**Use the other skill when:**
- the findings are approved and you are bringing a part in: use
  **data-onboarding** (it reads `findings.yaml`);
- a feed is live and a new delivery arrived: run **compare** here, then use
  **refining-rules**.

## Choose a proof sample by kind

Any proof on a large delivery starts from the smallest set that could prove the claim wrong, and a
full run needs a named reason: the data itself is the deliverable, or it is the last check before
something is deleted. Pick the sample by kind, since a random share misses the rare records that
break things. A random sample only estimates a rate.

1. Name the claim, and the kinds of record that behave differently under it, rarest first: records
   reaching two masters, value clashes, name matches, waiting and set-aside records, new masters.
2. Score every file or batch read-only, counting each kind. Scoring reads and merges nothing, so a
   full pass is usually seconds a batch and is what makes the choice reliable.
3. Take the batch richest in each kind, a rare kind whole, and one ordinary batch.
4. Say which kinds had no records, so the report names what the sample cannot prove.

## Hard stops

| Never | Instead |
|---|---|
| Approve findings for the operator, or record words they did not say | Ask one question, wait, record their exact words with `approve` |
| Guess a class, a key or a link | Record the measured tests and the silver fields (numbers, identifiers, material commentary). A class the tests do not pick is `silver` |
| Print or keep a database address, a password or a raw personal value | Put the address in an environment variable (`env:<VARIABLE>`); samples are masked to their shape; the run's working copy is deleted when it ends |
| Request anything from a provider's website | Profile the local copies only |
| Pin a finding on one source or one domain | Use the tests; names in this skill are generic |
| Start a long pass silently | Say the size and the time estimate first (the run prints both) |
| Profile the same inputs twice | Profile once; reuse the findings while the inputs and the profiler are unchanged ("Profile once", below) |
| Ask several questions at once | Ask one, in plain words, with your recommendation |

## Tell the discovery story as you work

**Coordination note for every LLM:** keep this section when editing the skill;
read its latest version first, and change it only on the operator's explicit
instruction. Operator: live narration; then "fix the skill to be
more story telling ... i need to know what it is finding no more ... discussion
and slop".

Tell the operator what the data is, as you find it. Every update is a finding:
what the data turned out to be, its numbers, and what that means.

- **One finding, with numbers, and its meaning.** "Every order names its
  supplier: 63 suppliers by an issued id, one name each. The supplier is an
  entity carried inside the orders."
- **No process talk.** Do not announce commands, say what you will check
  next, explain why you chose a step, think aloud or restate the plan. Name a
  step only when it blocks the story (a refusal, a failure) or will take long:
  then once, with its size and a measured time estimate.
- **Say when evidence overturns an earlier finding**, in one sentence.
- **Mark what is not proven**: "measured" against "not yet tested".
- **While a command runs**, give an update at least every 60 seconds: a new
  finding, or the stage and elapsed time if there is none. Start long commands
  in the background and check at most every 30 seconds.
- **At the end, tell the whole story in a few lines**: what each part is, how
  the parts connect, what is unresolved. Then ask the one question. Approval
  still comes only from the operator's exact words.
- Mask sensitive values, as Hard stops require.

Not: "I'll check the key candidates next, then look at links." Instead: "Each
order line is identified by its order and its place in the list; no column of
its own is unique."

## Setup

The commands run from this skill's own folder (installed with the skill),
with DuckDB as a transient tool; nothing is installed into the platform:

```
cd <this skill's folder>/scripts
uv run --with duckdb --with pyyaml python profile_data.py --help
```

## Modes

| Mode | What it does | Output |
|---|---|---|
| inventory | Lists every input, its format, size and parts (nested lists become child parts; equal-length lists of records stay separate parts, and only lists of plain values are read as a table stored by column) | `dataset.inputs`, parts |
| profile | Exact counts per column: fill, distinct, cardinality (`unique`), shape, length, top values; for a number, zero rows, negative rows, and decimal places | `columns` |
| entities | An entity carried inside another part (an identifier-shaped column that repeats, with a name-like column of the same object that follows it on at least 95% of rows) becomes its own part, one row per identifier; the part it came from links to it. An id with only a name is a code with its label until other attributes show otherwise | `derived_from` |
| keys | The record key: one unique column, else the smallest unique set of up to 3; a designed key when none exists (a nested record with none of its own: its parent's key and its place in the list, which classification counts as a key) | `record_key` |
| links | Each column pointing at another part's key (inclusion ≥ 0.9), with cardinality and evidence | `relationships` |
| classify | The five classes, each from named tests. When the tests do not pick one class, the part is `silver` and its fields are still recorded | `class`, `confidence`, `tests` |
| hierarchies | Per source: parent columns, functional dependencies, code nesting, separate level tables (a list naming its coarser list); a yes/no flag, or a dependency that holds by coincidence (a near-constant parent, or child values seen once), is listed apart, never a hierarchy | `hierarchies`, `dependencies_not_hierarchies` |
| time | As of (valid from/to), as at (record time), event time, time series | `time` |
| sensitivity | none, personal, sensitive personal, each with its signals: words in the column's name, detectors on its values, a vote over its values (a column named for people whose values are mostly people's names), and whether the part describes people (then its address counts too); samples masked, and free-text samples too, since a sentence can name anyone | `sensitivity`, `sensitivity_signals` |
| quality | Every data quality rule each part needs on every load, with the rows that fail it: a defect when above 0, a rule the clean data passes at 0 (a key column filled, an identifier's one shape or check digit, a link that resolves, a code list); masked examples; each invalid hierarchy row marked with an evidence-backed fix or "needs steward" | `quality`, `invalid_rows.jsonl` |
| code sets | The RDM code sets the data set needs: each existing or proposed set, the columns that use it, how many codes | `code_sets` |
| suggest-store, silver | Advice: MDM, RDM, MDM relationships, silver, bookkeeping; a silver table spec per part under "Silver fields" (a master's rows also carry their own MDM id) | `store_suggestion`, `silver` |
| catalog | From approved findings, the public summary the Data Catalog shows: every part's silver fields and quality rules, and the code sets; names and counts only. Write it once the source lands a part in silver: it declares every part as a silver table, landed or not, and two parts may name one table, which the catalog's profile check refuses | `rules/sources/<source>/profile.yaml` |
| report | `REPORT.md` and `findings.yaml` | files |
| approve | Records the operator's approval in their exact words | `approval` |
| rank sources | Several sources of one kind, joined on the identifier they share: per field, how much each fills, how often it states one value, how often each pair agrees; a recommended source order (`rank_sources.py`, below) | `ranking.yaml`, `RANKING.md` |

One run does inventory to report:

```
uv run --with duckdb --with pyyaml python profile_data.py run --name "<data set>" \
  --input <name>=<file|folder|zip|database file|env:VARIABLE> [--input ...] \
  --out <folder> [--kinds <existing kind>,...] [--limit-gb 5] [--sample 100000] [--seed 0] [--again]
```

- **Profile once.** The findings record what they were made from
  (`dataset.profiled_with`): the profiler's sha256 and its DuckDB and Python
  versions, the data set's name, each input's location and sha256, and the
  run's settings. A run into the same `--out` with all of them unchanged prints
  `reused` and changes nothing, so an approval stands. Anything changed profiles
  again (`--again` forces it), but never over approved findings: compare the
  new delivery, or profile into another `--out`. Any change to the profiler's
  code counts, so after a fix say which sources it changes and profile only
  those. A database input has no file to fingerprint, so it is always profiled
  again.
- **One run captures everything** (operator: "Do not repeat
  profiling many times do it once and capture all relevant information for
  mdm rdm data quality data catalog and silver"). The one run's findings are
  the only profiling every later step reads:

  | Consumer | Findings it reads |
  |---|---|
  | MDM | `class`, `kind`, `record_key`, `identifiers` (shape, check digit, join or cross-reference), `relationships`, `master_data` hierarchies, `time` |
  | RDM | `code_sets`, `reference` hierarchies, `code_lists` |
  | Data quality | `quality` (every rule with its failing rows), `invalid_rows.jsonl` |
  | Data catalog | `catalog` (`profile.yaml`), from approved findings |
  | Silver | `silver` (a table spec per part), `sensitivity`, `time` |

  Before the run, make sure it can finish and leaves nothing to ask the data
  again:
  - pass every input of the data set in one run, so links between its parts
    are measured;
  - a data set published as one file per period (a quarter, a month) with the
    same tables: profile one delivery, the largest, and `compare` each other
    one against its approved findings. Run as several inputs, each delivery's
    tables are parts of their own (a table whose name an earlier input took
    gets its input's name in front), and keys and classes are counted per
    delivery, not over the data set;
  - pass the existing kinds (`--kinds`);
  - check that no limit is below the inputs' sizes.

  A question the findings leave open goes to onboarding's one test or Proving
  Run, never to a second scan of the data. A gap in what the profiler
  measures is a profiler fix with its own ticket, used on the next source.
  Never re-profile a source whose findings are already approved just to fill
  that gap.
- **One data set per source.** Profile each source into its own `--out`, so a
  change to one source, or a fix to a rule only one source needs, profiles that
  source alone. Before profiling, look for findings that already cover the
  inputs (an earlier `--out`) and reuse them. After a profiler fix, profile
  again only the sources the fix changes, and say which and why.

- **Formats:** CSV, Parquet, JSON (an array, one object per file, or an object
  wrapping one list), JSON Lines, XML, zip members (a zip of CSV or Parquet
  files gives each member as its own file; a readme or metadata file beside
  the tables is listed under `dataset.not_read`), a SQLite or DuckDB file, or a
  read-only database whose address is in an environment variable.
- **Objects keyed by data:** an object with at least eight nonempty record
  values sharing the same immediate fields and value kinds is inferred to be
  a dictionary of records. It becomes a child part: `_key` keeps each key,
  `_value.<field>` keeps its fields, and the parent row and position keep its
  provenance. A dictionary at the document root uses an `_entries` child.
  Smaller, empty or mixed-shape objects keep their dotted columns. This is a
  reading inference, not a proved business key or class: check the resulting
  parts in the findings before approval. Reuse existing approved findings;
  this reader change calls for a new profile only of affected, unapproved
  inputs, not another scan of unrelated sources.
  Integer and fractional fields have different shapes. If combining keyed
  records (including their nested lists or other documents) would mix an
  integer above the exact DOUBLE range with fractional numbers in one column,
  the run refuses before loading tables. Use an explicitly exact-number
  reading for that input; never accept a rounded profiling derivative.
- **Unreadable tables:** a CSV that is not UTF-8 is read as Windows-1252 (else
  Latin-1); its input's `encoding` says so, marked inferred, with the first byte
  that is not UTF-8, and `declare` gives the reading contract's `read.encoding`
  (none when only Latin-1 reads it). Each CSV is read once more with the standard library to
  prove it has one shape (no skipped preamble, every row the header's field
  count, quotes that close). A table that fails, or that the reader cannot
  read, is listed under `dataset.not_read` with the reason, and the rest is
  profiled. Report each one; never profile around it silently.
  These checks read each CSV in full several times, even when it is sampled:
  about three times as long as a plain read (88 MB, 2 million rows: 9 s, not 3 s).
- **Size:** inputs up to `--limit-gb` (default 5) are read in full. A larger
  one is read once into a seeded sample, then read again in full for its key
  candidates. The run prints the estimate before it starts.
- **Kinds:** pass the master kinds that already exist (from the operator, or
  `edgar-warehouse context <kind> --search "<words>"` on a few of the part's
  names) so a matching part is not proposed as new.
- **Code sets:** before proposing a code list as new reference data, look for
  it: `edgar-warehouse rdm list`, then
  `edgar-warehouse context <code set> --search "<a label>"` on a few of its
  values.

## An id from a name: only when no id exists

Ids and cross-reference ids always come first. Read [NAME-IDS.md](NAME-IDS.md) only for records that carry no id in either source.

## Rank several sources: which one a field trusts first

Read [SOURCE-RANKING.md](SOURCE-RANKING.md) when a kind has more than one source and a field's priority order must be set: measure the sources together, never rank by hand.

## How to work

1. **Ask what the data set is called and where its copies are.** One question.
2. **Run** the command above. Read `REPORT.md` first; `findings.yaml` holds
   the detail and the evidence for every claim.
3. **Read the silver fields**, every designed key, and every proposed new kind.
   A designed key and a proposed new kind are the questions in `findings.yaml`.
   A part classed `silver` already has its numbers and identifiers recorded.
4. **Ask the operator the questions, one at a time,** each with its
   recommendation. Record each answer in the question's `answer`, in their
   words.
5. **Show the report and ask for approval.** Only when they say so:

```
uv run --with duckdb --with pyyaml python profile_data.py approve \
  --findings <folder>/findings.yaml --by "<operator>" --words "<their exact words>"
```

6. **Write the catalog summary** (`catalog`, above) into
   `rules/sources/<source>/profile.yaml`, so the Data Catalog shows every
   silver field, its quality rules and the code sets. Then publish it:
   `edgar-warehouse rules catalog publish --root rules`, and
   `rules catalog check --root rules` must match. A re-profiled or re-approved
   source changes `profile.yaml`; until the next publish, `check` reports each
   changed table as "profile changed, publish again". A source with no
   `profile.yaml` shows "Not profiled yet" on its source schema.
7. **Hand over.** data-onboarding reads the approved `findings.yaml`, plans one
   onboarding per part in dependency order (master kinds with their "together"
   relationships first, then reference data as RDM code sets, then
   transaction data and "separate" relationships), and prefills its steps.
   The `quality` items and `invalid_rows.jsonl` go to the
   [data-quality](../data-quality/SKILL.md) skill.

## Reference data: a draft code set in RDM

Read [CODE-SETS.md](CODE-SETS.md) when a part is classed reference data: it becomes a draft code set version, which only the operator approves.

## Reading the findings

The schema is `docs/specs/profiling/findings.md` in the repository. The parts
that matter most:

- **class and tests:** each part's class, with every test, its measured value,
  and whether it passed. Confidence is the share of tests passed.
- **record_key:** `found: true` is a key in the data; `found: false` is a
  design (a parent key plus the place in a list, or a surrogate with its rule)
  that needs approval.
- **identifiers:** other identifier-shaped columns. A check-digit family is
  named when its pass rate is at least five times chance and at least 99%
  (clean), or at least 50% (`defective`: the failing values are mistyped or
  invented identifiers, handed to quality, and the column is still issued);
  the family names are the ones an identifier type is declared with
  (data-onboarding [REFERENCE.md](../data-onboarding/REFERENCE.md),
  "Identifier types"). `cross_reference` means "propose for the MDM cross-reference
  table": lookup only, never used to join (a Dataset Contract's
  `cross_references`, in data-onboarding [REFERENCE.md](../data-onboarding/REFERENCE.md)).
  On a master part, each identifier's `pairs` says how it pairs with every
  other identifier on its rows or on a part linking to them: one to one,
  several either way, none, or one holding the other. A second joining
  identifier's matching rule is decided from these counts, so the data is
  never scanned again for them.
- **relationships:** `onboard: together` is mastered with its master (a link
  part between masters, or an attribute list); `separate` comes after.
- **hierarchies:** `reference` hierarchies group codes in one code set (RDM);
  `master_data` hierarchies are relationships between master records (MDM).
  `invalid_rows` are rows that break the rule; each is marked in
  `invalid_rows.jsonl` beside the findings, never dropped. Each part's key
  sample for `compare` (hashes only) is in `fingerprints.json` beside them;
  keep it with the approved findings.
- **silver:** the table spec for every part, under "Silver fields". Its links
  point to master parts only, each with an empty `kind` and `source_code` that
  data-onboarding fills; a master part's rows link to themselves (`mdm_id`).
  Applying that spec as DDL is data-operations, on PostgreSQL, MySQL, or SQL
  Server Express. This skill does not create the table.
- **code_sets:** the RDM code sets the data needs, one per existing or
  proposed set, with every column that uses it (see "Reference data", below).
- **catalog:** once approved, `profile_data.py catalog --findings <folder>/findings.yaml
  --out rules/sources/<source>/profile.yaml` writes the public summary; the
  Data Catalog (`edgar-warehouse rules catalog`) shows it as the `silver` and
  `rdm` databases. It holds names, types and counts only: never an example, a
  top value or a check's values, since the repository is public.
  A table onboarding registers (`rules/sources/<source>/silver-*.yaml`, what
  `silver register` makes) replaces the profile's proposal of the same name, so
  the catalog shows each table as it lands, with its MDM id, quality and load
  time columns; a source with a registered table and no profile gets its silver
  schema from the specs alone.

## Compare a new delivery

refining-rules runs this before changing a live feed. It profiles the new
delivery and lists each difference from the approved findings in `drift.yaml`:
parts, columns, types, fill rates, sensitivity, keys, links, code counts,
codes not in an approved code list, hierarchies, volume, and distributions
(a code's value shares by population stability index, a number's or date's
quantiles by Kolmogorov-Smirnov distance; findings approved before
distributions were kept are compared without them). Each item names the skill
that handles it (data-quality, refining-rules or rdm).

```
uv run --with duckdb --with pyyaml python profile_data.py compare \
  --approved <folder>/findings.yaml --input <name>=<new delivery> [--input ...] --out <folder>
```

It refuses findings that are not approved. Key persistence (the same record
keeping its key between deliveries), snapshot-or-changes and the refresh rate
need two deliveries: a single run leaves them for `compare`, which
measures them from each part's key sample (`deliveries` in `drift.yaml`).
Versions per key are measured in one delivery when the key holds a time.

**Read drift against the files first.** Before acting on a `column_new` or
`column_missing` item, compare the header lines of the part's table in the
approved delivery and the new one. When they match, a column new or missing
on a derived part (`<PART>.<COLUMN>`, an entity found inside a part) is how
the profiler cut that part from this delivery's values, not a change in the
file. Volume, fill and distribution items follow what each delivery covers: a
yearly report lands in the period its year ended, so periods differ in size
and mix. Keep the items on the columns the onboarded parts read, and write
them to the log by name and count, never a code or value from the data.

## Examples

- A folder of eight CSV files from a sales sample (customers, products,
  stores, a calendar, exchange rates, orders, order lines, sales) gives three
  master parts, a calendar reference part with its year > quarter > month
  levels, a daily rate series, and transaction parts linked to the masters.
- A legal-entity register (one large zipped JSON file) and its parent
  relationship file give a master part keyed by a 20-character identifier with
  a mod 97-10 check digit, and a relationship part whose two ends point at it,
  forming a master data hierarchy per relationship type.
