# Source Contract

Status: **proposed**, 2026-09-21. Planning only: this document implies no
code, migration or edit to any Clean MDM file. Written from the resolved
tickets of the [Source Contract](../../../.scratch/source-contract/map.md)
wayfinder map, which hold the reasons. This document holds the rules.
Codex builds the real engine from it. The throwaway prototype that proved it
is in [`.scratch/source-contract/prototype/`](../../../.scratch/source-contract/prototype/README.md).

A contract author needs only this document and one example contract (§22).
If you had to read engine code to write a contract, this document is wrong:
report it.

## 1. Purpose

Today a new source means a new Python parser, a silver table written by hand
in three places, and a hand-written Clean MDM adapter. A **Source Contract**
replaces all of that with **one file per source**. The file declares:

1. how the source's Bronze Artifacts are read (`read`);
2. the silver table the source produces (`silver`);
3. how silver rows map into MDM (`dataset`, Clean MDM's own Dataset Contract);
4. the tests and data checks that prove it (`tests`, `checks`, `gate`).

Adding a source becomes a file, not a module. Operator's framing
(2026-09-21): *"how easy is to bring new data in and master and test just
using configuration input file"*.

## 2. Scope

**In:** everything from an existing Bronze Artifact to a Clean MDM source
publication, and the tests that prove it.

**Out:**
- getting data into bronze (fetch, schedule, SEC access);
- where silver is physically stored after Snowflake;
- generating Step Functions from config;
- retrofitting the existing parsers;
- the Mastering Policy rules themselves
  ([policy language](../mdm/policy-language.md)). This document only fixes
  their authoring convention (§4.4).

## 3. Terms

All terms are defined in [`CONTEXT.md`](../../../CONTEXT.md):
- the contract and its documents: **Source Contract**, **Dataset Contract**,
  **Mapping Document**, **Bronze Artifact**, **Artifact Family**;
- what a contract calls: **Primitive**, **Named Convention**, **Custom Step**;
- how it is proven and activated: **Named Case**, **Batch Gate**, **Proving
  Run**, **Rules Database**, **Rule Activation Approval**;
- the MDM side: **Mastering Policy**, **Identifier Contract**, **Source Record
  Binding**.

A contract may use no other domain term (acceptance check 7).

## 4. Where contracts live, and their lifecycle

### 4.1 The Rules Database is the master

- The **Rules Database** is a Postgres database of its own, separate from
  Clean MDM's `mdm_v2`. It is local first. It holds every version of every
  Source Contract and Mastering Policy, with its state, its proof and its
  approval (ticket 06 Q1–Q2).
- YAML is the authoring and export format. The database stores each version
  as canonical JSON with its SHA-256 digest. A stored version never changes.
- Custom code (`custom.py`) and fixtures stay files. A stored version records
  their digests. **Proposed** (not decided by a ticket): the runner refuses
  a version whose recorded digests do not match the files.
- **Production never reads the Rules Database.** When a version becomes
  active, the Dataset Contract is registered into Clean MDM through
  `register_dataset`, and a Mastering Policy through `register_policy`.
  Production merges read only `mdm_v2`, pinned by digest.
- **Proving Run merges happen beside the Rules Database** (ticket 06 Q3–Q4),
  in a throwaway database created for the run and dropped after it, never in
  production. The prototype used a throwaway Postgres 16 container for this.

### 4.2 Lifecycle

`draft → proven → active → retired`

| State | Enters when | By whom |
|---|---|---|
| draft | `source save` stores a validated new version | agent |
| proven | a Proving Run passes every named case, every check and the Batch Gate (§16) | agent |
| active | the version is registered into Clean MDM (§4.1) | agent, **or** a person — see §4.3 |
| retired | a newer version of the same source becomes active; kept for replay (ticket 06 Q3) | the activation that replaces it |

A failed Proving Run leaves the version in draft. The failed run is kept as
a record. **A contract with no `gate` can never become proven**: passing
cases alone leave it in draft (ticket 09 found the prototype said "proven").

### 4.3 Who activates

- A version whose changes **only add data** may be activated by the agent
  (ticket 06 Q3, option z). Where that line falls for a given change is the
  agent's to state and the operator's to overrule.
- A version that **can bind or merge identities** needs a **Rule Activation
  Approval**. The agent must explicitly ask the operator before it makes
  the version active; an approval is never inferred from silence or from an
  earlier approval. The approver, the time and the exact digest approved are
  stored with the proof.

### 4.4 One authoring convention for both languages

The Mastering Policy is authored the same way as a Source Contract (ticket 04
Q2a):
- strict YAML 1.2, stored as canonical JSON;
- the same path rules;
- the same `primitive: {arguments}` call shape;
- a published JSON Schema.

The rules themselves don't change, only how they are written. The stored
JSON may keep the shape Codex's `register_policy` expects. A kind-level
`default_sources` list, with per-field exceptions, makes "SEC first" one line
a reviewer can check (handover item 5).

### 4.5 Commands

| Command | Does |
|---|---|
| `source save <file.yaml\|folder>` | load → validate → store an immutable draft version in the Rules Database. Initialization is `source save` over a folder of contracts (ticket 06 Q2) |
| `source export <name> <version>` | write a stored version back out as YAML (line numbers in errors refer to this output) |
| `source prove <name\|file> [--gate] [--json] [--all]` | run a **Proving Run** (§17). `--all` prints every violation instead of a sample |
| `source run [--source <name>]` | production: parse new Bronze Artifacts for every active contract (§18) |
| `source mapdoc <name\|file>` | print the generated Mapping Document (§20) |

**Not prototyped:** `save`, `export`, the Rules Database schema, lifecycle
states and approvals are design only. The prototype stored proofs as files.

## 5. The source folder

```
sources/<name>/
  contract.yaml                     the Source Contract (authoring copy; the Rules Database holds the master)
  custom.py                         optional: this source's Custom Steps
  fixtures/…                        Bronze Artifacts for Named Cases
  fixtures/families/<family>/…      lookup targets for Named Cases (§10)
  MAPPING.md                        generated; never edited by hand
```

Nothing outside the folder may name the source (acceptance checks 1–3). The
one exception is machine configuration: where each Artifact Family's files
sit on a given machine. That is environment configuration, like a deployment
setting, and is not part of any contract.

## 6. File format

- **Strict YAML 1.2, with every plain scalar read as text** (ticket 04 Q0).
  PyYAML reads YAML 1.1 and must not be used. YAML 1.2 alone is not enough:
  `ruamel.yaml` 0.19 in 1.2 mode keeps `NO` as text, but still turns `010`
  into the integer 10, `2026-09-21` into a date and `1e3` into a float. The
  loader must read plain scalars as strings; the JSON Schema and the
  primitive tables then give each argument its type. The prototype's loader
  did not do this: it kept YAML's numbers and turned dates back into text
  (finding 15).
- **Stored as canonical JSON**: sorted keys, no whitespace. The digest is its
  SHA-256. Comments stay in the YAML and never enter the digest. A reason
  that must survive storage goes in a `why:` field, not a comment.
- **Errors name a line and a rule.** This includes YAML syntax errors.
  Example: an unquoted `LegalName[*]` is read as a YAML alias. The loader
  must turn that into `yaml-syntax` at the right line, with a hint that paths
  have no wildcards (prototype finding 3).
- **JSON Schema.** The tables in this document are normative. The real
  schema is generated from them and must enforce every primitive's argument
  list, so editors autocomplete it and validation names the keyword. The
  prototype's `contract.schema.json` is illustrative only: it checks
  structure, and the prototype checked arguments in Python.
- **YAML anchors and merge keys** (`&name`, `<<:`) are Open (§25, item 1).
  The prototype used them once, to share eleven transaction columns.

## 7. Top-level keys

| Key | Required | Meaning |
|---|---|---|
| `source` | yes | the source code: lowercase dotted, e.g. `gleif.level1`. Becomes Clean MDM's `source_code` |
| `version` | yes | the author's version label (a prototype convention). The digest, not the label, identifies a version |
| `bronze` | yes | `{ family: <Artifact Family> }`: what `source run` reads |
| `requires` | if `custom.py` imports anything outside the standard library | distribution names, e.g. `[edgartools]` |
| `read` | yes | §8 |
| `lookups` | no | §10 |
| `silver` | yes | §12 |
| `dataset` | to reach MDM | §13 |
| `checks` | no | §14 |
| `tests` | yes (at least one Named Case) | §15 |
| `gate` | to become proven | §16 |

## 8. `read`: from a Bronze Artifact to rows

### 8.1 Readers

| `format` | Options | Produces |
|---|---|---|
| `xml` | `envelope: sgml_text` (take the `<XML>` block of a full SEC `.txt` submission and expose its header fields); `root: <tag>` (any other root gives zero rows); `on_parse_error: no_rows \| retry_without_control_chars` | one document |
| `json` | none: the whole artifact is **one document** (e.g. one SEC company profile per file). `records: jsonl`: one document per line. `record_path: <path>`: the record inside each document | one document per artifact, or per line |
| `csv` | `columns: { <path-safe name>: "<header text>" }` (required), `delimiter` (default `,`), `encoding` (default `utf-8`) | one document per row, keyed by the names in `columns`; other headers are ignored. **Proposed:** an artifact that lacks a listed header, or whose bytes are not in the declared encoding, is rejected whole and counted in `rejected` |
| `bytes` | none | no document. Every table must use a `custom_reader` (§11) |

**A Source Contract is for a Bronze Artifact with a fixed shape.** The three
readers above cover XML, JSON and CSV. A source whose artifact has no fixed
shape — an HTML document such as a DEF 14A proxy, where each company lays its
Summary Compensation Table out differently — is **out of scope for a
contract** and keeps a hand-written parser (operator decision, 2026-09-22). A
second reason stands behind the first: reading such a table needs state
across rows (the executive's name is on the first row of a block and the
following rows carry only the wrapped title), and a table reads each row on
its own. `bytes` with a `custom_reader` can technically carry such a source,
but then the source is custom code in a contract's clothing, and the Mapping
Document would report it as ~100% custom.

**An empty CSV cell is `""`, not missing.** The header exists, so the value
exists; `default` does not apply. Chain `{ empty_to_null: {} }` on an
optional column, or `int`/`number`, which give `default` for `""`.

**Why `csv` needs a `columns` map (proposed, ticket 09):** real headers are
not path-safe. SEC Form ADV headers are `1A`, `1E1`, `1F1-Street 1`: they start
with digits and contain spaces and hyphens, and paths allow no quoting. The
map gives each header a path-safe name in one reviewable place:
`columns: { legal_name: "1A", crd: "1E1", street_1: "1F1-Street 1" }`.

A reader **yields documents one at a time** (an iterator, not a list), so a
large artifact streams. A streaming reader for zipped JSON arrays (the full
GLEIF Golden Copy) is needed and was not prototyped (§26).

### 8.2 The canonical tree

Every reader produces the same tree, so one path form reads XML and JSON:
- an element or object is a map;
- text is under `$`;
- an attribute is under `@name`;
- a child that occurs once is a map, and a child that repeats is a list in
  document order;
- a namespace prefix is kept, as in `prefix:Name` (GLEIF's `gleif:conformity`).

GLEIF's JSON already has this shape. XML is converted to it.

**Plain JSON values sit at their key.** Most JSON has no `$`: in
`{"cik": "0001001385", "tickers": ["DHC", "DHCNI"]}` the path is `cik`, not
`cik.$`. `$` exists only where the source itself puts text under `$`
(GLEIF) or where XML was converted. **`$` on a plain value is an error**
("use `.` for the value itself"). An item of a list of plain values is
read with `.`: `join: { each: tickers, parts: [ { text: { path: ".", default: "" } } ], … }`.
(Ticket 09: the trial agent copied GLEIF's `path: $` onto a list of strings;
the prototype silently gave `""` for every item.)

### 8.3 Paths

A path is keys joined by `.`. Each key is exactly one of:
- `$`;
- a name, optionally prefixed: `Name` or `prefix:Name`;
- an attribute: `@name` or `@prefix:name`.

The single path `.` means "the current item".

A path has no wildcards, indexes, filters, functions or quoting. The rule is
a **whitelist**: the prototype's first "no dots or spaces" rule wrongly
accepted `"LegalName[*].$"`. A path that starts with `@` must be quoted in
YAML (`"@id"`).

At run time:
- **A missing path gives the `default`. JSON `null` is not missing** (ticket
  04 Q1; research 10 §3): a path that reaches an explicit `null` gives
  `null`. The prototype treated both as missing, which changed nothing on its
  two sources but is a deviation the real engine must not copy.
- **Crossing a list in the middle of a path is an error** that names the
  location: "path crosses a repeating group; use each". It is never a silent
  first match.
- **Ending at a map where text is needed is an error**: "add `.$` or use
  `text_all`".

### 8.4 Tables

```yaml
read:
  tables:
    <silver table name>:
      each: <path>                  # one row per item; "." = one row per document
      where: { has: [<child>, …] }  # keep only items that have every listed child
      columns:
        <column>: <expression>
    <other table>:
      custom_reader: { step: <name>@<n> }   # instead of each/where/columns (§11)
```

- For `each`, a single map counts as a one-item list, and a missing path
  gives zero rows. That rule settles GLEIF's "object or list" fields once.
- `where` runs **before** `ordinal` numbers the rows.
- Paths inside a table are relative to the item. `from: document` reads from
  the document root instead.
- A table has **either** `columns` **or** a `custom_reader`, never both.

### 8.5 Expressions

A column is exactly one of:
- one call: `{ <primitive>: { <arguments> } }`;
- a chain: `{ steps: [ <call>, <call>, … ] }`, where each step after the first
  receives the previous value;
- a Custom Step: `{ custom: { step: <name>@<n>, inputs: { … } } }`;
- inside `custom.inputs` only: the name of a column already computed in the
  same row.

A primitive without arguments is still a call with an empty map:
`{ upper: {} }`, `{ ordinal: {} }`, `{ empty_to_null: {} }`.

No string is ever run as code. `contains: "see remarks"` is a literal, and
`regex:` is a literal pattern.

## 9. Primitives

These are the 24 in the prototype. **Every primitive that returns a
value read from a path (`path`, or `each` for `join`) requires an explicit
`default:`**, because this repo has three different "absent" results (`""`,
`null`, `false`). `count` is the exception: a missing group is 0. The spec is
stricter than the prototype in two places, and says so: the prototype did not
require `default` on `value_with_footnotes` or `join`.

**Readers:** they read the current item, or the document with `from: document`.

| Primitive | Required | Optional | Returns |
|---|---|---|---|
| `text` | `path`, `default` | `from` | the text at a `$` or `@attr` path, stripped |
| `text_all` | `path`, `default` | `from` | all text under an element, in order, stripped. Use it where an element mixes text and children |
| `int` | `path`, `default` | `from` | an integer, or `default` if the text is not a whole number |
| `number` | `path`, `default` | `from` | a double, or `default` |
| `flag` | `path`, `true_set`, `default` | `from` | `true` if the stripped text is in `true_set`, otherwise `false`. `default` applies only if the value is missing |
| `date_prefix` | `path`, `default` | `from` | the leading `YYYY-MM-DD` of the unstripped text, otherwise `default` |
| `timestamp` | `path`, `default` | `from` | the text as written, which must be ISO 8601 (`2012-06-06T15:51:00.000Z`). It does **not** convert time zones (gap G4, §24); the prototype accepts any text |
| `date_format` | `path`, `format`, `default` | `from`, `to` (`date` or `timestamp`) | **Proposed** (ticket 09; not yet used by a trial agent — round 3 wrote a Custom Step before it existed). Text in a declared `strptime` format (a literal pattern, e.g. `"%m/%d/%Y %I:%M:%S %p"`) → ISO date, or ISO timestamp with `to: timestamp`. Text that does not match gives `default`. It adds no time zone (gap G4). Added in ticket 09 for Form ADV's `03/17/2026 11:29:59 AM` |
| `value_with_footnotes` | `path`, `default` | `from` | **Named Convention.** SEC's `<x><value/><footnoteId id/></x>` as `"value [F1,F2]"` |
| `header` | `name` | `default` | a field of the reader's envelope header, e.g. `ACCESSION NUMBER` |
| `artifact` | `name` | — | an artifact attribute; `sha256` today |
| `const` | `value` | — | the literal |
| `ordinal` | — | — | the 1-based position of the item after `where` |
| `count` | `each` | `from` | how many items a group has (missing = 0) |
| `join` | `each`, `parts`, `default` | `from`, `separator` | for each item, the `parts` (expressions) joined, stripped; the items joined by `separator`. No items gives `default` |
| `ref` | `lookup` | — | the lookup result record (§10) |

**Chain steps:** each takes the previous value.

| Primitive | Required | Optional | Returns |
|---|---|---|---|
| `upper` | — | — | uppercase text |
| `strip_spaces` | — | — | the text with every space removed |
| `starts_with` | `value` | — | `true` or `false` |
| `empty_to_null` | — | — | `null` for `""`, otherwise unchanged |
| `when` | `contains`, `then` | `ignore_case` | the value of the `then` expression if the text contains the literal, otherwise unchanged |
| `get` | `path`, `default` | — | the value at a path in the previous value (a lookup record) |
| `len` | `path`, `default` | — | the length of a list at a path in the previous value |
| `to_text` | — | `default` | the previous value as text; `null` gives `default` |

**Rules for adding a primitive** (ticket 04 Q2):
- By default, add a small primitive.
- A **Named Convention** is admitted only if all four hold:
  1. it names a published format convention;
  2. two or more sources or columns use it;
  3. it has its own unit-test table in the engine;
  4. it has a one-line vocabulary entry that shows the chain it replaces.
- Logic that belongs to one source is a Custom Step (§11), never a primitive.

Every primitive is versioned `name@n`; an unversioned name means `@1`, and
`@1` and `@2` live side by side so old versions replay.

**One descriptor per primitive is the source of truth.** The engine keeps one
descriptor per `name@n`: each argument's kind (path, expression, expression
list, literal), whether it reads the item or takes the previous value,
whether `default` is required, and which argument the Mapping Document
shows. The JSON Schema, the validator and the Mapping Document are generated
from these descriptors, and a test checks the tables above against them. The
prototype spread this over five places (GoF review of ticket 08).

### 9.1 Engine structure: one declaration per extension point

The prototype changed the same places each time the trial found something.
The real engine must have **one declaration** for each kind of thing a
contract names, and derive everything else from it:

| Extension point | One declaration holds | Derived from it |
|---|---|---|
| primitive | arguments and their kinds, previous-value or item, `default` rule | schema, validator, §9 tables (checked by a test), Mapping Document |
| reader (`format`) | options schema, validation, a function that yields documents, the rule for rejecting a whole artifact | schema, validator, §8.1 table |
| expectation (`expect.silver`, `expect.mdm[].deferred`, `expect.mdm[].evidence_only`, `expect.merge[].outcome`) | the checker and the diff it reports as `{column, expected, actual}` | the `expect` schema. **A key with no checker makes the contract invalid** |
| gate metric (`rejected`, `type_errors`, `deferred`, `rows.<table>`, `check.<label>`) | its name pattern, its `max_pct` base, how it is computed | limit-name validation and the gate, from one list; the §16 table is checked against it |

In the prototype, gate names were validated in one place and computed in
another; that mismatch is how an unknown `deferred:` limit went unnoticed
(GoF review of ticket 09).

## 10. `lookups`: another Artifact Family

```yaml
lookups:
  owner_submissions:
    family: sec.submissions_main          # an Artifact Family, never a path
    key: owner_cik                        # a column already computed in the row
    select: { as_of: { header: { name: FILED AS OF DATE } }, fallback: earliest_after }
```

- **Selection (ticket 04 Q3):** take the copy captured on or before `as_of`.
  If none exists, `fallback: earliest_after` takes the earliest copy after
  it; `fallback: none` (a prototype addition, not a ticket decision) returns
  "not found". This is repeatable, because
  bronze only gains later-dated captures. The capture date is the date in the
  bronze path, which is the fetch date by construction
  (`edgar_warehouse/infrastructure/dataset_path_catalog.py:215-219`). S3
  object times are **never** capture times: every submissions object carries
  2026-07-19, the account-migration copy.
- **Result record:** `{found, artifact_sha256, payload, selected}`, read with
  `ref` then `get`/`len`. Record `artifact_sha256` on the row, so the copy
  used can be named.
- **Never fetches.** A missing copy gives `found: false`.
- **Named Cases read the source folder's own `fixtures/families/<family>/`**,
  never machine bronze, so a case gives the same result on every machine
  (prototype finding 5). The fixture folder uses the family's own layout, so
  a dated family's fixtures are dated and exercise `as_of`. The prototype
  supported only a flat `<key>.json` layout there.
- **Artifact Family names** are listed by the engine's family registry
  (`source families`, proposed), named `<authority>.<name>`
  (`sec.submissions_main`, `gleif.level1_records`). A contract names a family;
  the registry, per machine, says where its files are.

## 11. Custom Steps

Custom code lives in the source's `custom.py` and registers itself with one
of three shapes:

| Shape | Declared as | Signature | Use |
|---|---|---|---|
| **value step** | `custom: { step: name@n, inputs: {…} }` in a column | named inputs → one value | one column that primitives cannot compute (Form 3/4/5 `owner_display_name@1`) |
| **table reader** | `custom_reader: { step: name@n }` on a table | Bronze Artifact bytes → rows | a document no reader can parse (HTML tables) |
| **custom check** | `custom_check: { step: name@n, table, inputs: […] }` in `checks` | named inputs → `null` or a problem message | a data rule the built-in checks cannot state |

```python
# sources/<name>/custom.py — the engine provides the decorators and Reject
from source_contract import Reject, check_step, table_reader, value_step

@value_step("owner_display_name", version=1)
def owner_display_name(raw: str, cik: int | None, submissions: dict) -> str: ...

@table_reader("summary_comp_table", version=1)
def summary_comp_table(raw: bytes):            # yields dicts: the rows of the ONE table that names it
    yield {"exec_name": "…", "fiscal_year": 2025}

@check_step("owner_name_has_letters", version=1)
def owner_name_has_letters(owner_name_raw: str) -> str | None:   # None = fine
    ...
```

The module name `source_contract` is the real engine's to choose; the
prototype called it `source_engine`. **Steps are registered per source**:
two sources may each have an `owner_kind@1`, and a duplicate `name@n` within
one source is a load error. (The prototype used one registry shared by every
source, where a later source would silently replace an earlier one's step.
That is harmless for one source per process, and wrong for `source run`,
which loads every source — GoF review of ticket 08.)

The six rules (ticket 04 Q4), for every shape:
1. **Inputs are named in the contract.** The code sees nothing else.
2. **The output is checked** against the declared silver column or table. An
   undeclared column, or a wrong type, is a located failure.
3. **No side effects**: no network, no file writes, no MDM call. The runner
   calls each step twice on fixtures; a step whose results differ is a bug
   (exit 3).
4. **Imports are declared** in `requires` (distribution names). The engine
   maps modules to distributions with `importlib.metadata`, never a
   hand-written alias, and refuses an undeclared import.
5. **Versioned** `@n`. Changing the logic means a new `@n`, and the old one
   stays for replay.
6. **Bad data is rejected, bugs stop the run.** A step may raise
   `Reject(reason)`; the runner counts it against the gate (`rejected`) and
   continues. Any other exception stops the run with exit 3, naming the step,
   the version and the record.

## 12. `silver`

```yaml
silver:
  <table>:
    key: [<column>, …]
    columns: { <column>: <type>, … }       # type: string | bigint | double | boolean | date | timestamp; suffix ? = nullable
    collapse: <rule>                       # map decision Q7; grammar Open (§25 item 6)
```

- What each type accepts: `string` text; `bigint` a whole number; `double` a
  number; `boolean` `true`/`false`; `date` an ISO `YYYY-MM-DD` text;
  `timestamp` an ISO 8601 text. Dates and timestamps are text in silver, and
  their form is checked.
- The `read` columns and the `silver` columns must be the same set;
  otherwise the contract is invalid.
- Every output row is type-checked. A mismatch is a **located failure**
  (exit 1) pointing at the silver column. It is not an engine bug (prototype
  finding 4).
- A column that counts real-world records uses `bigint`, never a small
  integer (repo rule in `CLAUDE.md`).
- A contract may declare **more than one silver table**. Only
  `dataset.table` feeds MDM; the others are evidence. Use a child table for a
  repeating group whose members carry their own attributes (for example
  former names with their dates), instead of joining them into one column.
  A child row takes its parent's key with `from: document`:

  ```yaml
  sec_company_former_name:
    each: formerNames
    columns:
      cik:         { text: { path: cik, from: document, default: null } }   # the parent's key
      name_index:  { ordinal: {} }
      former_name: { text: { path: name, default: null } }
      valid_from:  { text: { path: from, default: null } }
  ```

  The Mapping Document marks such a column "(from the document)".
- The table's physical schema and its collapse rule are generated from this
  block (map decision Q7). The collapse grammar (for example, the latest row
  per key by a declared order) is not yet fixed and was not prototyped.
  Where silver is stored is out of scope.

## 13. `dataset`: into MDM

```yaml
dataset:
  table: <the silver table that feeds MDM>
  contract: <Clean MDM Dataset Contract, including its adapter block, unchanged>
```

The `contract` is Clean MDM's own Dataset Contract. Its `adapter` block is
read by Clean MDM's `normalize`
(`edgar_warehouse/mdm/clean/adapters.py:49-158`), one silver row to one
assertion. The prototype carried Codex's `publication_v1/dataset.json` into
a contract verbatim (JSON is YAML 1.2), and `normalize` mapped it as
expected.

### 13.1 Adapter keys

The full reference, with `path:line` evidence for every key and every
rejection, is in
[research 01](../../../.scratch/source-contract/research/01-mapping-language-reference.md).

| Key | Required | Meaning |
|---|---|---|
| `version` | yes | adapter version. It enters every `assertion_id` (§23) |
| `kind` \| `kind_field` + `kind_values` | one of them | a fixed kind, or an exact, case-sensitive lookup with no fallback |
| `record_key` (+ `record_key_format`) | yes | list of silver columns. One part gives the plain value; several give a JSON array string |
| `identifiers` (+ `identifier_formats`) | no | namespace → column; `identifier_formats` is namespace → format. **A namespace is not a format.** Clean MDM's SEC Company source uses `identifiers: { cik: cik }` with `identifier_formats: { cik: sec_cik }` (`edgar_warehouse/mdm/clean/company_source.py:50-51`). Writing `sec_cik` as the namespace silently skips formatting (ticket 09). Name a namespace after the issuing register, lowercase (`cik`, `lei`, `crd`); where the Mastering Policy has an Identifier Contract for it, use that contract's namespace. Only `sec_cik` exists as a format (gap G3); an identifier with no format is kept as written |
| `fields` | no | MDM field → column. A name not in the Mastering Policy is evidence only |
| `field_shape` | no | one scalar at the top of the adapter: `field_shape: nullable_text` (every field must be text or null). Any other value is silently ignored |
| `profiles` | no | Governed Role Profiles: `role` (literal), `authority` (literal), `registration` (column; null skips the profile), `valid_from` (column, required, time-zone aware), optional `jurisdiction`, `valid_to`, `fields` |
| `relationships` | no | reported edges: `type` (literal, a Clean MDM relationship type), `target_key` (columns), `target_source` (literal source code), `valid_from` (column, required, time-zone aware), optional `scope` (literal), `valid_to`, `properties` |
| `source_record_provenance` | no | **set it to `true`** (gap X3): without it, a re-ordered file mints new assertions |
| `provenance` | no | source values copied into provenance |
| `retain_deferred` | no | unsupported records become deferred evidence instead of failing the batch |

Every column the adapter names must be a column of `dataset.table`; the
validator checks it. Literal keys (`role`, `authority`, `type`,
`target_source`, `scope`) look like paths but are not (gap X2).

### 13.2 Rules the code applies that a contract author must know

- A path through a list gives `null` with no error. So each row of
  `dataset.table` must already be **one assertion**; `read` does the
  fan-out.
- **Within one publication, a record key may appear only once.** Clean MDM
  stores one assertion per `(source_code, record_key, publication_key)`
  (`edgar_warehouse/mdm/migrations/023_clean_mdm.sql:50`). Round 3 of the
  trial keyed Form ADV silver by `filing_id` but the adapter by `crd`, and one
  adviser filed 15 times in March. Its merge case passed only because those
  filings carried the same mapped value, so their assertions were identical
  and the second insert was a no-op. Any difference would have failed the
  batch. **Proposed rule:** either make the adapter's record key the silver
  key (here `filing_id`, with `crd` as an identifier, so binding brings the
  filings to one identity), or collapse to one row per record key first (the
  Open collapse rule, §25 item 6). The validator should check that the
  adapter's `record_key` columns are unique in `dataset.table`.
- Relationships whose target key is missing are dropped with no record (gap
  F5), and target keys are never formatted (gap F4).
- A field value that is a map with `"op"` is an operation. Use
  `field_shape: nullable_text` unless an operation is intended.
- `semantics` is never read: fields always behave as patches and collections
  as snapshots, so emit the complete identifier, profile and relationship set
  on every row.

### 13.2a Which fields a source can win

A mapped field wins in MDM only if the **active Mastering Policy** ranks
this source for that field of that kind (Field Survivorship). A field the
policy does not rank for the source is kept as evidence only, and the
Mapping Document says so. So a new source that should *win* a field needs
**two** things: its own Source Contract versions, and a new Mastering Policy
version that ranks it. The policy is a separate document in the Rules
Database with its own approval (§4.3), not a file in the source folder.
Acceptance check 1 covers the source's own versions. A policy change is a
deliberate, separately approved step, because ranking a source changes
other sources' winners.

**Map a field only if its values mean the same thing** as the MDM field's
values from other sources. SEC state-of-incorporation codes (`DE`, `V8`) are
not GLEIF jurisdiction codes (`US-DE`): mapping one onto `jurisdiction` would
let two vocabularies compete in one field. Keep such a column as evidence,
or convert it with a declared step first.

### 13.3 Other Dataset Contract parts

Only `family`, `schema_version`, `publication_families`,
`publication_contract` and `registry_evidence` change behaviour. `provider`,
`record_key`, `publication_key`, `effective_time` and `semantics` are required
but free text. Until Codex fixes closed value sets (research 01 §3,
**PROPOSED**), write them like this:

| Part | Write |
|---|---|
| `provider` | the authority's short name: `SEC`, `GLEIF`, `IAPD`, `PCAOB` |
| `family` | the Clean MDM source-registry family the artifacts come from (for SEC submissions, `submissions`). It must match the registry, so it is checked at registration. A provider with no registry family yet needs one registered first: that is part of onboarding the Artifact Family, done outside the source folder, like `families.local.yaml` |
| `schema_version` | `silver-<dataset table>-v<N>` |
| `record_key` | the adapter's `record_key` in words, e.g. `zero-padded 10-digit CIK` |
| `publication_key` | what identifies one publication, e.g. `capture run plus artifact sha256` |
| `effective_time` | `unknown` or `publication`. With `unknown`, a field can win only where the Mastering Policy also sets `allow_unknown_effective` for it — part of the same policy change that ranks the source (§13.2a). A source the policy does not rank needs nothing here |
| `semantics` | `patch` |
| `completeness` | optional (not required by Clean MDM, not read by code): `bounded_sample`, `full_baseline` or `delta` |

Never author `registry_evidence`: `register_dataset` adds it.

### 13.4 The identity kind (blocking for sources whose kind is decided by a rule)

The adapter needs a kind for each row **at mapping time**. For Form 3/4/5
reporting owners, the kind is decided by **rule C-J**, a Mastering Policy
classification. Three answers exist:

| Answer | Status |
|---|---|
| `kind_values` over `owner_entity_type` (research 01, F3) | **rejected**: `entityType` is not a person-or-company classification. That gap is why C-J exists |
| a Custom Step computing the kind (the prototype's `owner_kind@1`, using edgartools' classifier) | **stand-in only**, for parse and mapping tests. It is not C-J and must not reach production |
| the Dataset Contract defers the kind to the Mastering Policy's classification rules | **the spec's position**, proposed to Codex (handover item 6). The adapter names a classification rule set instead of a kind, and the Merge Stage classifies before binding |

**Record key for Form 3/4/5 (gap F2, not decided).** The prototype keyed
owners by `(accession_number, owner_index)`, so every filing makes a new
subject for the same owner. Research 01 proposes `owner_cik` as the subject
key, with `(accession, owner_index)` kept only as a provenance locator. This
must be settled before Form 3/4/5 goes live (§25 item 7).

**The same trap on a company source (ticket 09).** On SEC company
profiles, `kind_values: { operating: company }` over `entityType` looks
right, but `other` covers people **and** listed foreign companies (Wisekey,
Brookfield Wealth Solutions, Oddity Tech in the 400-document batch). A row
whose kind value is not in `kind_values` becomes a **deferred record**, and
the Batch Gate counts it in `deferred`, whose limit is 0 unless declared
with a `why:`. So a contract that maps most of its batch away cannot become
proven by accident: it has to say how many rows it leaves out, and why.

Until Codex accepts one of these, a source whose kind needs a rule must not
go live. Form 3/4/5 is also blocked by the open Person projection and privacy
item (gap F6; policy language §15 item 4). Its parse and mapping cases run
today.

## 14. `checks`

```yaml
checks:
  - not_null:  { table, column }
  - unique:    { table, columns: [...] }
  - in_set:    { table, column, values: [...] }
  - pattern:   { table, column, regex: "<literal>" }
  - row_count: { table, min }
  - custom_check: { step: name@n, table, inputs: [<column>, …] }
```

How `null` counts: `not_null` counts `null` and `""`; `in_set` counts `null`
as a violation unless `null` is one of the values; `pattern` skips `null`;
`unique` treats `null` as a value like any other.

A check is named in the gate as `check.<name>(<argument>)`, where the
argument is the column, the comma-joined columns, or the step:
`check.not_null(lei)`, `check.unique(accession_number,owner_index)`,
`check.custom_check(owner_name_has_letters@1)`. Two checks with the same
name would collide (the same check on a same-named column in two tables), so
names must be unique: give one of them `label: <text>`, and the gate uses
`check.<label>`:

```yaml
  - not_null: { table: sec_company_former_name, column: cik, label: former_name_cik_present }
```

Every check returns **violations**, each with the row's silver key and a
message, never a bare true or false. Checks run in every Named Case (where
any violation fails the case) and in the Batch Gate (where each has a limit).

## 15. `tests`: Named Cases

```yaml
tests:
  - case: <what this proves, in words>
    fixture: fixtures/<file>                 # or a list: [fixtures/a.json, fixtures/b.json]
    given:
      identities:
        <name>: { fixture: fixtures/<file>, record: <record key> }
    expect:
      silver: { <table>: [ { <column>: <value>, … }, … ] }    # rows in order; only listed columns compared; row count exact
      mdm:    [ { kind, identifiers: {…}, fields: {…}, evidence_only: [<column>, …] }, … ]   # Clean MDM assertions, in row order
      merge:
        - { record: <key>, outcome: bound, to: <name> }
        - { record: <key>, outcome: binding_required }
        - { identity: <name>, field: <field>, value: <v>, winner: <source> }
```

- **Named Cases are required.** Each known trap gets one: an object where a
  list is expected, a row the `where` filter drops, a value next to a
  footnote.
- **A deferred record in `expect.mdm`** is written `{ deferred: <reason> }`,
  e.g. `{ deferred: unsupported_identity_kind }` for a row whose kind value is
  not in `kind_values`. A case about the identity kind must list its `mdm`
  expectations: a case that leaves `mdm` out checks nothing about MDM (ticket
  09, round 2).
- **Cut fixtures from real artifacts** where possible: whole records, bytes
  unchanged (for CSV, the header line plus whole rows, line endings kept).
  **Proposed:** a made-up fixture says `SYNTHETIC` in its case name, as the
  prototype's own synthetic cases do.
- **`fixture`** is one file or a list of files. For a family with one
  document per artifact, a case about two records lists two files. Rows are
  concatenated in list order. A fixture that does not exist makes the
  contract invalid (exit 2).
- **`evidence_only`** lists silver columns that must not **win** an MDM
  field (ticket 05 Q2). That is the same meaning "evidence only" has in
  §13.2a: a column is evidence only if the adapter does not map it, or maps
  it to a field the active Mastering Policy does not rank this source for. A
  listed column that would win a field is a failure.
- **Unknown expectation keys make the contract invalid** (the schema closes
  every `expect` entry). Ticket 09 round 3 found the prototype accepting an
  expectation it never checked; §9.1 gives the structure that prevents it.
- **`given.identities` are seeds.** They go through the same contract and a
  first Merge Stage batch with a declared Steward binding, never inserted
  rows. They are named by the case, never by a generated id. `record` is the
  record key as the adapter builds it, after `record_key_format` if one is
  declared: the plain value for a one-part key, the JSON array string for a
  multi-part key. Quote it in YAML when it has leading zeros
  (`record: "0001001385"`).
- **Merge outcomes:** `bound`, `new`, `binding_required`, `deferred` (with
  reason), `quarantined`, and a field's value and `winner`. The prototype
  implemented `bound`, `binding_required` and field value/winner only.
- **`bound` checks a declared binding** until Codex provides a test mode for
  automatic rules (handover item 1). The runner reports which one it
  checked.
- **Order and cost:** parse and mapping cases run first and need no
  database; Postgres starts only if a case has `merge:` (ticket 05 Q2). Merge
  cases need a local Docker daemon; on macOS the runner uses Colima's socket
  unless `DOCKER_HOST` is set. Merge
  cases need a throwaway Postgres 16 (§4.1). The prototype measured about 10–15 s for one case,
  including container start, with a 60 s readiness limit. Research 03 saw
  an 8 s wait fail 4 of 7 runs on Colima.
- **A snapshot is optional**: a regression net, not intent. A changed
  snapshot is re-recorded only by a command that prints the row-level diff,
  and the Proving Run records who accepted it.

## 16. `gate`: the Batch Gate

```yaml
gate:
  batch: { family: <Artifact Family>, select: all }        # or: { sample: { size: 5000, seed: 7 } }
  limits:
    rejected:                     { max_pct: 0.5, why: "…" }
    type_errors:                  { max: 0 }
    deferred:                     { max_pct: 2.0, why: "…" }
    rows.<table>:                 { min: 300000 }
    check.<check>(<arg>):         { max: 2, why: "…" }
  snapshot: optional                                          # a regression net (§15)
```

- **Metrics:** `rejected` (Custom Step rejects), `type_errors` (a prototype
  addition, from finding 4), `deferred` (records the Merge Stage defers;
  decided in ticket 05, **not prototyped**), each check, `rows.<table>`, and
  an optional snapshot comparison.
- **`rejected`, `type_errors`, `deferred` and every check default to 0.** A
  looser limit needs `why:`; the schema refuses one without it. `rows` has no
  default: it is judged only when a `min` is declared.
- **Limit names are a closed set**: `rejected`, `type_errors`, `deferred`,
  `rows.<a declared silver table>`, and `check.<a declared check>`. Any other
  name makes the contract invalid, with a "did you mean" hint. (Ticket 09:
  the prototype silently ignored an unknown `deferred:` limit, so a reviewer
  would have believed a limit was enforced.)
- A `rows` floor is judged on the pinned batch the proof names. For a
  growing family, set it to the batch the version is proven on; a later
  Proving Run on a larger batch is a new proof.
- **`max`** is an absolute count, **`max_pct`** a percentage of the rows in
  the metric's table (for `rejected` and `type_errors`, of all rows plus the
  rejected ones), and **`min`** an absolute floor.
- **The batch is pinned** by the SHA-256 of the list of its artifacts'
  SHA-256s. A sample must be seeded.
- **The proof stored with the version** contains:
  - the contract digest, the custom-code digest and the fixture digests;
  - the engine version and the batch hash;
  - each metric's value, percentage, limit and `why`;
  - the merge summary, pass or fail, the time, and the runner.
- **The gate proves the source contract only.** A binding rule still needs
  the policy language's precision proof and a Rule Activation Approval.

## 17. Proving Run output

The same facts come in two renderings. **`--json` is the primary interface**,
because agents do most testing and validation. The terminal rendering is for
human review.

```
FAIL  gleif/contract.yaml:72  case "address lines as a list, …"
      gleif_lei_record  row 1
        column    expected                actual
        lei       08IRJODWFYBI7QWRGS31X   08IRJODWFYBI7QWRGS31   ✗
      fixture: fixtures/three-records.jsonl
INVALID gleif/contract.yaml:15  /read/tables/gleif_lei_record/columns/lei/text/defualt  [argument-known]
      unknown argument 'defualt' for primitive text — did you mean 'default'?
prove gleif.level1@prototype-1: 2 cases, 0 failures  →  version proven
```

Each `--json` failure record contains:
- `kind`, `file`, `line`, and `pointer` (RFC 6901 into the contract);
- `case` or `metric`;
- `diff`, a list of `{column, expected, actual}`;
- `fixture`, and a location inside the data where one exists;
- for checks, `violations`, `limit` and sample row keys.

| Exit | Meaning |
|---|---|
| 0 | proven |
| 1 | a case, check, type or gate failure |
| 2 | the contract is invalid (YAML, schema, path, argument, silver/read mismatch, undeclared import) |
| 3 | an engine or Custom Step bug (fail closed) |

When cases pass but the gate was not run, the prototype exited 0 with state
`draft`. The spec requires a distinct code (Open, §25 item 2), so an agent
never reads 0 as proven.

## 18. Production: `source run`

- One command runs every active contract; no source has its own pipeline
  stage (acceptance check 1). What triggers it (a schedule, an event after a
  bronze capture, a Step Function step) is out of scope.
- It finds work by the contract's Artifact Family. The skip key is
  `(artifact sha256, contract digest)`, which keys idempotency on the durable
  artifact.
- It parses into silver with the same engine code as `source prove`, and
  publishes the rows to Clean MDM as a pinned source publication. The
  Merge Stage then applies the active Mastering Policy.
- `normalize` needs `publication_key`, `revision`, `effective_at`,
  `artifact_sha256` and `member` from the publication, not from the row
  (research 01 §1.4). `source run` must build them from the Artifact Family's
  publication rules. **Not prototyped:** the prototype passed fixed values.
- Unknown errors fail closed. Rejects are counted.

## 19. No network

The runner must not reach any network except, during merge cases, its
throwaway loopback Postgres. **This cannot be a Python patch.** The prototype
patched `socket.socket.connect` and allowed loopback only when the merge
harness asked, but `engine/nettest.py` showed two gaps:
- libpq, under psycopg2, opens its own socket in C. It reached for
  `10.255.255.1` and timed out.
- DNS lookups are not blocked: `example.com` was resolved before the connect
  was refused.

Run the Proving Run and `source run` in a container or network namespace
with no network, plus an explicit loopback allowance for the test Postgres.

## 20. Mapping Document

`source mapdoc` generates it from the contract and the adapter block. It has
one table per silver table, with these columns:
- the silver column and its type;
- where the value comes from in the Bronze Artifact (primitive and path,
  **custom** marked);
- where it goes in MDM: record key, identifier, field, identity kind, or
  *evidence only*.

It ends with the MDM kind and the **custom fraction** (check 11). It is never
hand-written, so it cannot drift from what runs.

## 21. Acceptance checks

| # | Check | How it is verified | Prototype |
|---|---|---|---|
| 1 | adding a source changes only its own folder and Rules Database versions | freeze the engine, add a source, list the commit's files | passed (7 files, all in two new folders) |
| 2 | deleting a source breaks nothing else | delete a folder; prove the others | passed |
| 3 | the engine names no source | grep the engine for source names | passed |
| 4 | no network | §19 | **partly**: needs enforcement below Python |
| 5 | a fresh agent onboards an unseen source from this spec and one example | ticket 09: three fresh agents, two sources | **partly**: all three proved their source with no engine read, but logged 14, 9 and 8 spec gaps; every one is written into this spec, and round 3's fixes are untested |
| 6 | the Mapping Document is generated | `source mapdoc` | passed |
| 7 | every contract term is in `CONTEXT.md` | grep the glossary for each term | passed (ticket 08 added six terms) |
| 8 | one command proves a source end to end | `source prove --gate` | passed |
| 9 | errors name the line and the rule | introduce a typo, a path error, a type error | passed after two fixes (findings 3–4) |
| 10 | GLEIF fits in about 100 lines with tests | `wc -l` | passed (93) |
| 11 | the custom fraction is shown | Mapping Document | passed (Form 3/4/5 3.3%, GLEIF 0%) |

## 22. Worked example: GLEIF Level 1

This is the complete contract, 93 lines. It reads real Golden Copy JSON
records, maps them into Company, and proves over 316 real records with one
declared exception. The Form 3/4/5 contract (227 lines, 2 Custom Steps,
equal to `edgar_warehouse/parsers/ownership.py` on 5,356 of 5,356 artifacts)
is at
[`prototype/sources/form345/`](../../../.scratch/source-contract/prototype/sources/form345/contract.yaml).

```yaml
source: gleif.level1
version: "prototype-1"
bronze: { family: gleif.level1_records }

read:
  format: json
  records: jsonl
  record_path: record          # the research extract's wrapper, not GLEIF's own envelope
  tables:
    gleif_lei_record:
      each: "."
      columns:
        lei:                 { text: { path: LEI.$, default: null } }
        legal_name:          { text: { path: Entity.LegalName.$, default: null } }
        legal_name_language: { text: { path: Entity.LegalName.@xml:lang, default: null } }
        legal_jurisdiction:  { text: { path: Entity.LegalJurisdiction.$, default: null } }
        entity_category:     { text: { path: Entity.EntityCategory.$, default: null } }
        entity_status:       { text: { path: Entity.EntityStatus.$, default: null } }
        legal_form_code:     { text: { path: Entity.LegalForm.EntityLegalFormCode.$, default: null } }
        legal_address_line1: { text: { path: Entity.LegalAddress.FirstAddressLine.$, default: null } }
        legal_address_more:  { join: { each: Entity.LegalAddress.AdditionalAddressLine, parts: [ { text: { path: $, default: "" } } ], separator: "\n", default: null } }
        legal_city:          { text: { path: Entity.LegalAddress.City.$, default: null } }
        legal_region:        { text: { path: Entity.LegalAddress.Region.$, default: null } }
        legal_country:       { text: { path: Entity.LegalAddress.Country.$, default: null } }
        hq_country:          { text: { path: Entity.HeadquartersAddress.Country.$, default: null } }
        registration_status: { text: { path: Registration.RegistrationStatus.$, default: null } }
        initial_registration: { timestamp: { path: Registration.InitialRegistrationDate.$, default: null } }
        last_update:         { timestamp: { path: Registration.LastUpdateDate.$, default: null } }
        managing_lou:        { text: { path: Registration.ManagingLOU.$, default: null } }

silver:
  gleif_lei_record:
    key: [lei]
    columns: { lei: string, legal_name: string, legal_name_language: string?, legal_jurisdiction: string?, entity_category: string?,
               entity_status: string?, legal_form_code: string?, legal_address_line1: string?, legal_address_more: string?,
               legal_city: string?, legal_region: string?, legal_country: string?, hq_country: string?, registration_status: string?,
               initial_registration: timestamp?, last_update: timestamp?, managing_lou: string? }

dataset:
  table: gleif_lei_record
  contract:
    provider: GLEIF
    family: golden_copy
    schema_version: gleif-level1-prototype-1
    record_key: LEI
    publication_key: golden copy publication
    effective_time: explicit publication effective time
    semantics: patch
    adapter:
      version: gleif-level1-prototype-1
      kind: company
      record_key: [lei]
      identifiers: { lei: lei }
      fields: { name: legal_name, jurisdiction: legal_jurisdiction, country: legal_country }
      source_record_provenance: true

checks:
  - not_null: { table: gleif_lei_record, column: lei }
  - unique:   { table: gleif_lei_record, columns: [lei] }
  - pattern:  { table: gleif_lei_record, column: lei, regex: "^[A-Z0-9]{18}[0-9]{2}$" }
  - in_set:   { table: gleif_lei_record, column: entity_status, values: [ACTIVE, INACTIVE] }

tests:
  - case: address lines as a list, as missing, and as a single object all read the same way
    fixture: fixtures/three-records.jsonl
    expect:
      silver:
        gleif_lei_record:
          - { lei: 08IRJODWFYBI7QWRGS31, legal_address_more: 300 DESCHUTES WAY SW STE 208 MC-CSC1, legal_country: US }
          - { lei: 21380089EIJRELKAIL21, legal_address_more: null, legal_name_language: he }
          - { lei: SYNTHETICOBJLINE0000, legal_address_more: 300 DESCHUTES WAY SW STE 208 MC-CSC1 }
      mdm:
        - { kind: company, identifiers: { lei: 08IRJODWFYBI7QWRGS31 }, fields: { name: Weyerhaeuser Company, country: US } }
        - { kind: company, identifiers: { lei: 21380089EIJRELKAIL21 }, fields: { country: IL } }
        - { kind: company, identifiers: { lei: SYNTHETICOBJLINE0000 } }
  - case: a record with a declared binding becomes that Company with the GLEIF name; an unbound record waits for binding
    fixture: fixtures/three-records.jsonl
    given:
      identities:
        weyerhaeuser: { fixture: fixtures/three-records.jsonl, record: 08IRJODWFYBI7QWRGS31 }
    expect:
      merge:
        - { record: 08IRJODWFYBI7QWRGS31, outcome: bound, to: weyerhaeuser }
        - { record: 21380089EIJRELKAIL21, outcome: binding_required }
        - { identity: weyerhaeuser, field: name, value: Weyerhaeuser Company, winner: gleif.level1 }

gate:
  batch: { family: gleif.level1_records, select: all }
  limits:
    check.in_set(entity_status): { max: 2, why: "GLEIF publishes the literal status NULL for 2 of the 316 records" }
```

## 23. Versioning and the immutable Dataset Contract (blocking)

The lifecycle in §4.2 **works only for the first version of each source**
today:
- Clean MDM stores one Dataset Contract body per `source_code`, forever
  (`edgar_warehouse/mdm/clean/store.py:217-224`: "Dataset contract is
  immutable; register a new versioned contract").
- `adapter.version` enters every `assertion_id`, and the store is unique on
  `(source_code, record_key, publication_key)`.

So activating version 2 of a contract needs a **new `source_code`**. That
gives every record a new subject (`subject = digest([source_code,
record_key])`), and those subjects need new bindings before they rejoin their
identities (research 01 rule 9).

This is the map's open **Change and replay** item. It needs a Codex decision
(handover item 4) before any source's second version can go live. First
versions are unaffected.

## 24. Dependencies on Clean MDM

These are sent to Codex as one note:
[`.scratch/handover/2026-09-21-claude-to-codex-source-contract.md`](../../../.scratch/handover/2026-09-21-claude-to-codex-source-contract.md).

**Blocking:**

| # | Item | Blocks |
|---|---|---|
| 4 | a versioning path for an immutable Dataset Contract (§23) | any second version |
| 6 | defer the identity kind to Mastering Policy classification (§13.4) | Form 3/4/5 and any rule-classified source |
| G3 | an `lei` identifier format, with unknown formats refused at registration | GLEIF identifiers formatted and validated |
| F4 | formatted relationship target keys; the reporting-owner row has no issuer CIK column (`ownership.py` emits `issuer_cik`, but silver drops it) | Form 3/4/5 `INSIDER_OF` |
| X1 | validate a Dataset Contract at registration (today any body is stored) | check 9 on the MDM side |

**Not blocking:** a test mode for automatic rules (item 1), a ≥30 s Postgres
readiness wait (item 2), a named offline registry authority (item 3),
authoring the Mastering Policy in this convention with `default_sources`
(item 5), deferral instead of silent relationship drops (F5), marking literal
keys (X2), `source_record_provenance` true by default (X3), relationship
type mapping and per-row effective time (G2, G5), time-zone-aware dates
(G4), a relationship-only dataset for GLEIF's separate relationship member
(G1), and a disposition for GLEIF reporting exceptions (G6). Two more are
ours to settle, not Codex's: the Form 3/4/5 subject key (F2, §25 item 7), and
Person projection and privacy (F6, policy language §15 item 4), which blocks
Form 3/4/5 go-live.

## 25. Open

1. **YAML anchors and merge keys.** Allow them explicitly, or add a named
   `columns_from: <table>` and forbid anchors. Anchors are standard YAML, but
   they are a second way to write the same thing.
2. **Exit code for "cases passed, gate not run".** It is 0 in the prototype;
   it needs its own code.
3. **Change and replay** (§23). When a new version becomes active, does
   `source run` re-parse old artifacts, and which identities re-project?
4. **Snapshot file format** and the re-record command.
5. **Moving an existing parser onto a contract.** Form 3/4/5 shows it *can*
   be done; the criteria for when it *should* be done are not set. Narrowed
   2026-09-22: only a fixed-shape source is a candidate, which today means
   the ownership parser (Form 3/4/5 XML, already proven equal on 5,356
   artifacts) and the ADV parser (CSV, the shape trial round 3 used). The
   proxy parser is out. The decision waits for the real engine, so the order
   rests on measured evidence, not a guess.
6. **The silver collapse grammar** (§12).
7. **The Form 3/4/5 subject key**: `owner_cik` or `(accession_number,
   owner_index)` (gap F2, §13.4).

## 26. What the prototype did not prove

- **The Rules Database** (`save`, `export`, states, approvals) is design only.
- **No network** is not enforced below Python (§19).
- **As-of lookup** was proven only on a synthetic dated layout. The local
  submissions copy is flat, so the Form 3/4/5 comparison could not test it.
- **The table reader** ran only on a synthetic 3-row HTML table, not a real
  DEF 14A.
- **GLEIF** was read from a 316-record JSONL extract. The streaming zip
  reader is not built, and `record_path: record` is the extract's wrapper.
- **Merge cases:** `bound` checked declared bindings only; `new`, `deferred`
  and `quarantined` were not implemented.
- **`source run`** and publication building (§18) were not prototyped.
- **Decided but not prototyped:** the collapse rule, and "JSON `null` is not missing" (the prototype treats `null` as
  missing). The `csv` reader, the `deferred` gate metric, the `date_format`
  primitive and the `evidence_only` check were added to the prototype during
  ticket 09.

## 27. Evidence

| What | Where |
|---|---|
| every decision, with reasons | [map](../../../.scratch/source-contract/map.md), tickets 01–07 |
| Mapping Language reference | [research 01](../../../.scratch/source-contract/research/01-mapping-language-reference.md) |
| parse needs of both proof sources | [research 02](../../../.scratch/source-contract/research/02-parse-needs-inventory.md) |
| mastering tests on a laptop | [research 03](../../../.scratch/source-contract/research/03-local-mastering-tests.md) |
| path and expression syntax | [research 10](../../../.scratch/source-contract/research/10-path-and-expression-syntax.md) |
| prototype, results, 15 findings | [prototype/README.md](../../../.scratch/source-contract/prototype/README.md) |
| equivalence with `ownership.py` | `prototype/expected-differences.md`, `prototype/equivalence.json` |
