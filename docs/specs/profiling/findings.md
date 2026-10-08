# Profiling findings (`findings.yaml`) and the silver table spec

Status: draft for operator approval (profiling ticket 01a). Research:
`.scratch/profiling/research/01-classify-and-profile.md`. Plan decisions 1–18.

`findings.yaml` is what the data-profiling skill writes for agents, and what
data-onboarding, data-quality and refining-rules read. `REPORT.md` says the
same in prose for the operator. Both are generic: any data set, any domain.

## 1. Rules for every value

- Every claim carries its **evidence**: the counts, the percentage, the test
  that produced it, and whether it came from a full scan or a sample.
- A claim without evidence is `unknown`, never a guess.
- Samples of fields tagged `personal` or `sensitive_personal` are masked to
  their shape (`Aaaa Aaaaa`, `999-99-9999`).
- Plain words, and the next step named, so an agent can act without asking.

## 2. Top level

```yaml
version: 1
dataset:
  name: <operator's name for the data set>
  inputs:                       # every file or table read
    - {kind: file|table, location: <path or db.schema.table>, format: csv|json|jsonl|xml|parquet|zip|postgres|sqlite|duckdb|snowflake,
       bytes: <n>, rows: <n>, sha256: <files only>}
  scan: {mode: full|sampled, reason: <e.g. "6.2 GB > 5 GB">, seed: <n|null>, elapsed_seconds: <n>}
  profiled_at: <ISO time>
  profiled_by: <agent and skill version>
parts: [...]                    # §3, one per table, file or child table
relationships: [...]            # §4
hierarchies: [...]              # §5
coincidental_dependencies: [...] # §5, dependencies that hold by coincidence, never hierarchies
questions: [...]                # §8, open questions for the operator, one at a time
approval:                       # §9
  status: draft|approved
  approved_by: null
  approved_words: null
  approved_at: null
```

## 3. A part

```yaml
- part: <name>                  # table, file, or child table (parent.list)
  parent_part: <name|null>      # for a child table made from a nested list
  rows: <n>
  class: master|reference|relationship|transaction|metadata|unknown
  confidence: <0..1>            # share of the class's tests that passed
  tests: [{test: <name>, value: <measured>, passed: true|false}]
  kind: <existing MDM kind|null>
  proposed_kind:                # when no existing kind fits (needs approval)
    {domain: <name>, kind: <name>, why: <plain words>}
  record_key:
    columns: [<col>, ...]
    found: true|false           # false = designed
    design: natural_composite|surrogate|null
    rule: <for a surrogate: how it is computed>
    evidence: {unique: true, null_rows: 0, persistence: <0..1|null>}
  identifiers:                  # other identifier-shaped columns
    - {column: <col>, shape: <pattern>, check_digit: <family|null>,
       pass_rate: <0..1>, chance_rate: <0..1>, fill: <0..1>, unique: <0..1>,
       proposal: cross_reference|record_key|none, why: <words>}
  columns:
    - {name: <col>, type: <detected>, fill: <0..1>, distinct: <n>,
       unique: <0..1>, top: [<masked samples>], role: <key|identifier|name|code|measure|date|text|flag|other>,
       sensitivity: none|personal|sensitive_personal}
  code_lists:                   # columns whose values are a code set
    - {column: <col>, distinct: <n>, label_column: <col|null>, code_set: <existing RDM code set|null>,
       proposed_code_set: <name|null>}
  time:
    delivery: snapshot|changes|unknown
    as_of: {from: <col|null>, to: <col|null>}      # valid time
    as_at: <col|null>                               # record time
    event_time: <col|null>
    versions_per_key: {p50: <n>, p99: <n>}
    series: {key: [<cols>], time: <col>, step: <duration>, gaps: <n>}|null
    refresh: <duration|unknown>
  quality:                      # handed to data-quality
    - {check: <id from the check list>, column: <col>, rows: <n>, examples: [<masked>],
       args: {<what a check needs: regex, values, family, length>}, why: <words>,
       proposal: exception|withhold|flag|blank, fix: <proposed fix|null>, fix_evidence: <words|null>}
  silver: <silver table spec, §6, for parts MDM does not own; else null>
  store_suggestion: {store: mdm|rdm|mdm_relationships|silver|bronze_only|bookkeeping, why: <words>, advisory: true}
```

### 3.1 Fields the first version also writes

Beyond the schema above, data-profiling 1 writes these, for the operator and
for drift: on a part, `scan` (full or sampled) and `runner_up` (the next class
and its score); on a column, `stored_type` (the type as stored; `type` is the
logical type a full read proves), `shape`, `shape_share` (masked shapes) and
`sensitivity_signals`; on an identifier, `local_counter`; on a record key,
`alternatives` (other unique keys) and, for a sampled part, `evidence.full_pass`.
A column's `role` may also be `link` (it points at another part's key).
`persistence` and `delivery` stay null and `unknown` until `compare` sees a
second delivery.

A record key designed on a name (research note 02; operator, 2026-10-05:
"Same record: durable key") also writes `basis` (the name column) and, in its
`evidence`, `unique_raw`, `unique_after_normalization`, `folded_collisions`
(groups of raw variants that normalize to one name, masked) and `provisional`
(true until a second delivery measures persistence). A name is never a found
key; the key is a durable id kept in a key map looked up by the sha256 of the
normalized name, and a rename is kept as an alias.

## 4. A relationship

```yaml
- relationship: <name>
  from: {part: <name>, columns: [<col>]}
  to: {part: <name>, columns: [<col>]}
  inclusion: <0..1>             # share of from-values found in to
  cardinality: 1:1|1:N|N:1|N:M
  via_part: <link part|null>    # for a link table
  role_column: <col|null>
  valid: {from: <col|null>, to: <col|null>}
  onboard: together|separate
  why: <words: e.g. "a role between two masters, mastered with the first">
  evidence: {test: rostin+zhang, score: <0..1>, scan: full|sampled}
```

## 5. A hierarchy

```yaml
- hierarchy: <name>
  type: reference|master_data   # reference: codes in one code set (RDM); master_data: relationships (MDM)
  part: <name>
  evidence_kind: parent_column|functional_dependency|code_nesting|level_tables
  levels: [{depth: 1, name: <proposed|null>, column: <col|null>, samples: [<codes>]}]
  rule: <e.g. "first 2 digits of the code are the parent code">
  holds: <0..1>                 # share of rows that follow the rule
  depth: <n>
  shape: balanced|ragged
  orphans: <n>
  cycles: <n>
  invalid_rows: <n>             # rows that break the rule; each marked in invalid_rows.jsonl (§5.1)
  valid_dates: {from: <col|null>, to: <col|null>}
```

A functional dependency between code columns is a level only when it is not a
coincidence (ticket 01d): it must predict the parent far better than always
guessing the parent's commonest value (a lift of at least 0.9 over that guess),
and at least half the rows must carry a child value seen on two or more rows.
One that fails is listed in `coincidental_dependencies` as
`{part, child, parent, held, baseline, lift, supported}` and is never a
hierarchy (a flag set on almost every row; a value seen on one row only).

### 5.1 Marked rows: `invalid_rows.jsonl`

Beside `findings.yaml`, one JSON object per invalid row of every hierarchy,
never inside the findings (it can be long):

```yaml
{hierarchy: <name>, part: <name>, key: {<record key column>: <value>}, column: <col>, value: <value>,
 reason: parent not found|names itself as its parent|on a cycle of parents|several parents|<parent> differs,
 fix: <value|null>, fix_evidence: <words|null>, needs_steward: <bool>}
```

A fix is proposed only with evidence: the one key equal to the value once
case, spaces and leading zeros are folded, or the parent most rows with the
same code have. Otherwise `needs_steward` is true. Values of a personal
column are masked. The part gets one `hierarchy_invalid` quality item with
the count.

The check list (`check` in a quality item): `missing` (an empty record key
column), `placeholder`, `shape_outlier`, `check_digit`, `code_list` (a small
code list, guarded as a whole; `rows` is 0), `link_not_found`,
`no_natural_key`, `hierarchy_invalid`. compare reports a code not in an
approved code list as `codes_new`.

## 6. The silver table spec

For every part MDM does not own: transaction and event data, and published
reference data (plan decision 13). The writer (plan row 6) reads this spec; the
spec does not depend on the store.

```yaml
table: <silver table name>
grain: <one row per ...>
columns:
  - {name: <col>, type: <logical type>, nullable: true|false, definition: <words>,
     source: <part.column or expression>, sensitivity: none|personal|sensitive_personal}
key: [<col>, ...]
links:                          # pointers to masters
  - {columns: [<col>], kind: <MDM kind>, source_key: <col>, mdm_id_column: <col>, inclusion: <0..1>}
time: {as_of: <col|null>, as_at: <col>, event_time: <col|null>}
partition: [<col>]              # e.g. a date
load_mode: append|upsert|snapshot
why: <plain words for each choice above>
```

Each link keeps the source's own key and an MDM id column filled after
mastering; a row whose entity is not mastered yet keeps an empty MDM id.

## 7. Drift (`compare`)

`compare` reads an approved `findings.yaml` and a new delivery, and writes
`drift.yaml`: new and missing columns, type changes, fill-rate changes beyond
a threshold, new code values, broken keys and inclusions, hierarchy rule
changes, and distribution shifts (KS or chi-square, PSI). Each drift item
names the skill that handles it: data-quality, refining-rules or RDM.

## 8. Questions

```yaml
- id: q1
  about: <part, column, relationship or hierarchy>
  question: <one question, plain words>
  recommendation: <answer and why>
  answer: null                  # the operator's exact words when answered
```

## 9. Approval

Data-onboarding refuses a `findings.yaml` whose `approval.status` is not
`approved`. Approval covers the classes, kinds, designed keys and hierarchies.
A proposed new domain or kind needs its own separate approval, recorded on
its question.
