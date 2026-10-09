---
name: data-profiling
description: Profile ANY data set (files of several formats, or a set of database tables) and find what each part is - master data, reference data, relationships, transaction data or metadata - with evidence. Finds keys, links between parts, code lists, hierarchies, time roles and personal data; writes REPORT.md for the operator and findings.yaml for agents; specifies silver tables; suggests a store (advice only). Use before onboarding a new data set (data-onboarding calls it), or to compare a new delivery with approved findings (refining-rules calls compare).
---

# Data Profiling

> Part of the **data-platform** skill set. This skill only reads data and
> writes findings. It never changes a store, a rule or a source.

Given a data set, it answers: **what is each part, and how do the parts
connect?** Finding the classes is the first job. The store suggestion is
advice only.

**Use the other skill when:**
- the findings are approved and you are bringing a part in: use
  **data-onboarding** (it reads `findings.yaml`);
- a feed is live and a new delivery arrived: run **compare** here, then use
  **refining-rules**.

## Hard stops

| Never | Instead |
|---|---|
| Approve findings for the operator, or record words they did not say | Ask one question, wait, record their exact words with `approve` |
| Guess a class, a key or a link | Report "unknown" with the failing tests, and ask |
| Print or keep a database address, a password or a raw personal value | Put the address in an environment variable (`env:<VARIABLE>`); samples are masked to their shape; the run's working copy is deleted when it ends |
| Request anything from a provider's website | Profile the local copies only |
| Pin a finding on one source or one domain | Use the tests; names in this skill are generic |
| Start a long pass silently | Say the size and the time estimate first (the run prints both) |
| Ask several questions at once | Ask one, in plain words, with your recommendation |

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
| inventory | Lists every input, its format, size and parts (nested lists become child parts) | `dataset.inputs`, parts |
| profile | Exact counts per column: fill, distinct, unique, shape, length, top values | `columns` |
| keys | The record key: one unique column, else the smallest unique set of up to 3; a designed key when none exists | `record_key` |
| links | Each column pointing at another part's key (inclusion ≥ 0.9), with cardinality and evidence | `relationships` |
| classify | The five classes, each from named tests; "unknown" when the tests do not decide | `class`, `confidence`, `tests` |
| hierarchies | Per source: parent columns, functional dependencies, code nesting, separate level tables (a list naming its coarser list); a yes/no flag, or a dependency that holds by coincidence (a near-constant parent, or child values seen once), is listed apart, never a hierarchy | `hierarchies`, `dependencies_not_hierarchies` |
| time | As of (valid from/to), as at (record time), event time, time series | `time` |
| sensitivity | none, personal, sensitive personal; samples masked | `sensitivity` |
| quality | Defects found on the way, with exact rows and masked examples; each invalid hierarchy row marked with an evidence-backed fix or "needs steward" | `quality`, `invalid_rows.jsonl` |
| suggest-store, silver | Advice: MDM, RDM, MDM relationships, silver, bookkeeping; a silver table spec for transaction and reference parts | `store_suggestion`, `silver` |
| report | `REPORT.md` and `findings.yaml` | files |
| approve | Records the operator's approval in their exact words | `approval` |

One run does inventory to report:

```
uv run --with duckdb --with pyyaml python profile_data.py run --name "<data set>" \
  --input <name>=<file|folder|zip|database file|env:VARIABLE> [--input ...] \
  --out <folder> [--kinds <existing kind>,...] [--limit-gb 5] [--sample 100000] [--seed 0]
```

- **Formats:** CSV, Parquet, JSON (an array, one object per file, or an object
  wrapping one list), JSON Lines, XML, zip members, a SQLite or DuckDB file, or
  a read-only database whose address is in an environment variable.
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

Ids and cross-reference ids always come first. Only for records that carry
none, in either source, is an id made from the name. A fixed precision bar
does not make a name safe: names one token apart are often different entities
(a share class, a series number, a legal form). So learn from the data first:

```
uv run --with duckdb --with pyyaml python match_names.py \
  --left <file> --left-key <col> --left-name <col> [--left-variants <col>] \
  --right <file> --right-key <col> --right-name <col> [--right-variants <col>] \
  [--same <left col>=<right col>] [--attribute <left col>=<right col> ...] [--personal] --out <folder>
```

- **Compare exactly:** token pairs that tell records with different keys apart.
  The id keeps them.
- **May fold:** variants seen on one entity (its other names, or a pair a
  shared id proves) and never apart. `name_id@1` does not fold them; the
  report counts how many records would pair one to one with them folded, as
  evidence for a later format version. A rename is not a variant: check the
  examples before proposing a fold.
- **Name alone cannot decide:** pairs seen both ways. A supporting attribute
  (one that agrees on proved pairs and separates near-homonyms) must decide;
  without one the records stay apart.
- **The id** (`name_id@1`): the name's tokens, every one kept, hashed. It is
  the engine's cross-reference format of the same name, so it goes into the
  MDM cross-reference table through the contract, with no code:
  `cross_references: {name_id: <name path>}` and
  `cross_reference_formats: {name_id: name_id@1}`. Like every cross-reference
  it is lookup only: `mdm.cross_reference_lookup('name_id', <id>)` finds the
  records of any source with that name; it never joins records.
- The report shows how many records it would pair one to one across the two
  sources, how many names are held twice (those pair nothing), and, on pairs a
  shared id proves, where the name id agrees and where it contradicts.
- Pass `--personal` when the names are people's, so examples keep their shape
  only.

Propose `name_id` only for a source whose records carry no id the other
sources share. Bring the operator the pairings and contradictions; never
present a name pairing where an id exists.

## How to work

1. **Ask what the data set is called and where its copies are.** One question.
2. **Run** the command above. Read `REPORT.md` first; `findings.yaml` holds
   the detail and the evidence for every claim.
3. **Check every "unknown"**, every designed key, and every proposed new kind.
   These become the questions in `findings.yaml`.
4. **Ask the operator the questions, one at a time,** each with its
   recommendation. Record each answer in the question's `answer`, in their
   words.
5. **Show the report and ask for approval.** Only when they say so:

```
uv run --with duckdb --with pyyaml python profile_data.py approve \
  --findings <folder>/findings.yaml --by "<operator>" --words "<their exact words>"
```

6. **Hand over.** data-onboarding reads the approved `findings.yaml`, plans one
   onboarding per part in dependency order (reference data, then master kinds
   with their "together" relationships, then transaction data and "separate"
   relationships), and prefills its steps. The `quality` items and
   `invalid_rows.jsonl` go to the [data-quality](../data-quality/SKILL.md)
   skill.

## Reference data: a draft code set in RDM

A part classed reference data becomes a code set version in RDM
(`docs/specs/rdm/spec.md`). Agents draft; only the operator approves.

1. **Look first:** `edgar-warehouse rdm list`, then
   `edgar-warehouse rdm describe <code set>` for what a code set means, where
   its values live and how to compare them. A code set that already exists
   gets a new version that names the current one in `supersedes`, never a
   second code set.
2. **Write the draft file** (JSON or YAML) from the approved findings:
   `{code_set: {code_set, name, definition, authority, steward}, version,
   created_by, evidence, supersedes, codes, labels, levels, crosswalk}`.
   - `codes`: each code with its `label`. A reference hierarchy gives each
     code one `parent_code`. An invalid row stays, with `status: invalid` and
     its `invalid_reason`.
   - `labels`: one `preferred` label per language, plus any `synonym`s.
   - `levels`: the names stewards gave each depth.
   - `crosswalk`: a code mapped to another code set, with `match_type`
     `exact`, `close`, `broad` or `narrow`. A standard RDM does not hold
     has `to_version: outside`.
   - `usage`: where the codes' values live (`store` mdm, silver, source or
     other; `object`; `field`) and how a value is compared (`exact` or
     `upper_trimmed`). Take it from the findings' columns that hold the codes.
   - `hints`: plain words for the next agent: `meaning`, `use_when`,
     `avoid_when`, `example_question`. Write only what the evidence shows.
   - `created_by`: the agent and this skill. `evidence`: the findings file.
3. **Draft:** `edgar-warehouse rdm draft --file <draft file>`.
4. **Ask for approval.** Show the operator the draft and
   `edgar-warehouse rdm diff <code set> <current> <draft>`. Record their
   approval only in their words:
   `edgar-warehouse rdm approve <code set> <version> --by "<operator>" --words "<their exact words>"`.
5. **Publish:** `edgar-warehouse rdm publish <code set> <version> --out <folder>`.
   `pin.json` there holds `{code_set, version, sha256}`, which a consumer pins.

A table kept as a map of code to fields drafts with
`edgar-warehouse rdm import-reference <name> --label <field> --crosswalk <field>=<code set>@<version>:<match type>`.
Every field must find a place (the label or a crosswalk), and the draft must
rebuild the table exactly, or nothing is written.

## Reading the findings

The schema is `docs/specs/profiling/findings.md` in the repository. The parts
that matter most:

- **class and tests:** each part's class, with every test, its measured value,
  and whether it passed. Confidence is the share of tests passed.
- **record_key:** `found: true` is a key in the data; `found: false` is a
  design (a parent key plus the place in a list, or a surrogate with its rule)
  that needs approval.
- **identifiers:** other identifier-shaped columns. A check-digit family is
  named only when at least 99% of values pass and the rate is at least five
  times chance. `cross_reference` means "propose for the MDM cross-reference
  table": lookup only, never used to join (a Dataset Contract's
  `cross_references`, in data-onboarding [REFERENCE.md](../data-onboarding/REFERENCE.md)).
- **relationships:** `onboard: together` is mastered with its master (a link
  part between masters, or an attribute list); `separate` comes after.
- **hierarchies:** `reference` hierarchies group codes in one code set (RDM);
  `master_data` hierarchies are relationships between master records (MDM).
  `invalid_rows` are rows that break the rule; each is marked in
  `invalid_rows.jsonl` beside the findings, never dropped. Each part's key
  sample for `compare` (hashes only) is in `fingerprints.json` beside them;
  keep it with the approved findings.
- **silver:** the table spec for a part MDM does not own. Its links point to
  master parts only, each with an empty `kind` and `source_code` that
  data-onboarding fills; `edgar-warehouse silver register` makes the table and
  `silver land` writes the part's rows into it.

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
need two deliveries: a single run reports them as unknown, and `compare`
measures them from each part's key sample (`deliveries` in `drift.yaml`).
Versions per key are measured in one delivery when the key holds a time.

## Examples

- A folder of eight CSV files from a sales sample (customers, products,
  stores, a calendar, exchange rates, orders, order lines, sales) gives three
  master parts, a calendar reference part with its year > quarter > month
  levels, a daily rate series, and transaction parts linked to the masters.
- A legal-entity register (one large zipped JSON file) and its parent
  relationship file give a master part keyed by a 20-character identifier with
  a mod 97-10 check digit, and a relationship part whose two ends point at it,
  forming a master data hierarchy per relationship type.
