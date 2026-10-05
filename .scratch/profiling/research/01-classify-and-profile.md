# Classify and profile any data set: research note

Ticket: [01 Research note](../issues/01-research-note.md). Plan: [plan](../plan.md) (decisions 1–38).
Written on 2026-10-04 (ET) on branch `claude/profiling-01-research`, at worktree commit `259f954c`.
No request was made to sec.gov. One public sample data set, Contoso V2 10k CSV (MIT), was downloaded to a scratch folder and checked with DuckDB.

**How to read the citations.**
- `[Sn]` points to the source list at the end.
- **(excerpt)** means the claim came from a search-result excerpt or a summary of the page, because the page itself blocked automated reading. Treat these as weaker than the rest.
- Rules marked **Proposal** are this note's own suggestions. No source states them; they are there for the operator to approve or change.

## Summary

1. **There is no free, testable standard definition of the five classes.**
   - ISO 8000-2 defines *metadata*, *identifier*, *authoritative identifier* and *proxy identifier* [S1].
   - Its master-data and transaction-data clauses, and DAMA-DMBOK, are paywalled.
   - So the classes are decided by **measurable tests** (section 1): whether the part has a key, how many other parts point at it, whether it grows, which date roles it has, and whether its identifiers are issued by someone else.
2. **Identifier detection can be generic.** It combines:
   - length and character-shape profiles;
   - pass rates for the check-digit families ISO 7064 mod 97-10, mod 11-2, mod 37-36, Luhn, Verhoeff and Damm [S5];
   - a comparison of each pass rate with its chance rate. Random strings pass mod 10 about 10% of the time, mod 11 about 9%, and mod 97 about 1%.
3. **Key and foreign-key discovery must be bounded.**
   - Finding all unique column combinations is NP-hard [S7].
   - No algorithm for finding functional dependencies handles 100 columns by 1 million rows [S13].
   - The approach: keys of at most 3 columns, near-inclusion at θ = 0.9 [S12], and the Rostin and Zhang foreign-key scoring rules [S12].
4. **Time.** Valid time ("as of") and transaction time ("as at") are the two SQL:2011 dimensions [S16].
   - Postgres temporal keys (`WITHOUT OVERLAPS`, `PERIOD` foreign keys) exist **only from PG18** [S17].
   - That conflicts with the plan's PG16 sandbox (decision 36).
5. **Sensitive data.** Detect it with a pattern, then a checksum or validator, then context words, then a vote per column. This is the Presidio and Google DLP approach [S20, S21].
   - "Sensitive personal" needs a defined meaning. GDPR Article 9 [S22] does not cover ID numbers.
6. **Drift.** Use schema diffs plus distribution tests: KS or chi-square, PSI, Wasserstein (Soda [S24]), KL divergence (Great Expectations [S25]), and rate-of-change rules (Deequ [S23]).
7. **Hierarchy storage.**
   - Published RDM versions are immutable, so the cost of editing a hierarchy does not matter at read time.
   - Store a **parent link** as the source of truth.
   - **Materialize** a readable path, level and depth **when a version is published**. A Postgres generated column cannot do this, because it cannot read other rows [S29].
   - An `ltree` column is an optional RDM-only index.
8. **Snowflake Postgres offers the needed extensions** [S48]: `ltree`, `pg_trgm`, `unaccent`, `fuzzystrmatch` and `btree_gist`, among roughly 80 more. It offers Postgres majors 16–18 [S49]. Full-text search is core Postgres.
9. **DuckDB core** reads CSV, JSON, NDJSON and Parquet, and attaches Postgres or SQLite read-only [S50].
   - It **cannot read XML or zip** without unofficial community extensions.
   - It **samples 20,480 rows** to detect types by default, so a "full scan" must set `sample_size = -1` [S50].
10. **Trial B.** Recommend **Contoso V2** (MIT, generated data, CSV and Parquet). Keep **Wide World Importers** (MIT) as the normalized, temporal second choice, and **AdventureWorks** (MIT) as a fallback (section 15).

---

## 1. Class definitions and distinguishing tests

### 1.1 What the sources say

| Class | Source definition | Status |
|---|---|---|
| Metadata | "data defining and describing other data" (ISO 8000-2:2020, 3.2.5, from ISO/IEC 11179-1) [S1] | verified |
| Identifier | "string of characters created by an organization to reference a data set" (3.3.1) [S1] | verified |
| Authoritative / proxy identifier | issued "by an organization that is the originator of the object identified or that is a legal authority" (3.3.6), versus issued by one that "is not the originator" (3.3.8) [S1] | verified |
| Master data | "data held by an organization that describes the key entities that are independent and fundamental … that it needs to reference to perform its transactions" (attributed to ISO/IEC 25024) [S3] | (excerpt) |
| Transaction data | ISO 8000-200 (draft) covers "events, certificates, measurements and transactions" [S2] | (excerpt) |
| Reference data | DMBOK2 puts Reference and Master Data in one knowledge area: "managing shared data to reduce redundancy … through standardized definition and use of data values" [S4] | verified overview only; the full text is paywalled |
| Permissible value | "Within a value domain, permissible values may either be enumerated or described"; a one-to-one "mapping of a single permissible value to a single value meaning is possible only when both … are enumerated, e.g. for code sets" (ISO/IEC 11179-3:2013/Amd 1:2020, 3.2.96) [S34] | verified |

The Gartner glossary was asked for as a secondary definition, but it returned 403 and was not used.

What follows from these:
- Reference data is the **enumerated value domain**: a list of codes, each with a meaning.
- Master data is the **independent entities that transactions point to**.
- Transaction and event data **records something happening**, and it points at masters.
- A **relationship** links two masters. ISO 8000 gives it no class of its own, but the plan does (decision 4).
- The ISO 8000-2 split between authoritative and proxy identifiers is the primary-source basis for the **issuer test**. It is also the basis for deciding which identifiers go to the cross-reference table (decision 6).

### 1.2 Measurable tests

**Proposal.** Each test is computed for each part (table, file or child table) and reported with its value, which is the evidence.

| Test | Master | Reference | Relationship | Transaction/event | Metadata/other |
|---|---|---|---|---|---|
| Has a single-column or composite unique key (section 3) | yes | yes (the code) | yes, made only of foreign keys (+ role, + start date) | yes (event id, or master key + timestamp) | often none |
| In-degree: parts with a column included in this key (θ ≥ 0.9) | ≥ 1 | ≥ 1, often many | 0 typically | 0 typically | 0 |
| Out-degree: foreign keys to other parts | few | 0, or 1 (to itself: parent) | ≥ 2 to masters (or 2 to the same master) | ≥ 1 to masters | — |
| Row count compared with the referencing parts | moderate | small (≤ 10,000; see #815 bounds in section 9) | ~ masters | largest | small |
| Growth between deliveries | grows with the business; same key, changed attributes | ~ constant; new versions | grows | append-only: new keys, old rows unchanged | per delivery |
| Name-like text columns (multi-token, high distinctness) | yes | label and definition only | no | no | no |
| Identifiers with a check digit or issuer shape | often | the code itself | no | rarely (the event id) | no |
| Date roles | lifecycle (created, inactive) and valid from/to | valid from/to; version | start/end | event time (+ record time) | run time, file time |
| Numeric measures (quantity, amount, reading) | few | none | rare (e.g. a percentage) | yes | counts, sizes, hashes |
| Values describe data (column names, file names, hashes, row counts) | — | — | — | — | yes [S1 3.2.5] |

- **Confidence** is the share of a class's tests that pass, with every failing test listed.
- If two classes tie, or none passes most of its tests, the result is **"unknown"** (decision 10).
- **Rule for telling reference from master (Proposal):**
  - reference: small, near-constant cardinality between deliveries, a code plus a label, and no name-like entity attributes;
  - master: grows with the business, and carries name-like attributes or issued identifiers.

## 2. Profiling metrics and generic identifier detectors

**Metrics per column.** Reuse the TestGen profiling query rather than re-deriving it (`.scratch/data-quality/research/01-datakitchen-testgen-observability.md`, section 1.1). It counts per column:
- values, nulls, distinct values;
- lengths and patterns;
- leading spaces, quoted values, digit-only values and dummy values.

Deequ's profiler adds completeness, approximate distinct count and inferred data type, in three passes with no shuffles [S23].

Add for this skill:
- the inferred type from a full read (section 14);
- min, max and quantiles;
- the top-k values;
- a character-class **shape** histogram (A = letter, 9 = digit, punctuation kept), as in TestGen's pattern;
- the fixed-length share;
- monotonic and dense integer runs.

**Identifier detector.** It is generic: no list of known identifier types.

| Signal | Computation | Proposal threshold |
|---|---|---|
| Fixed length | share of values with the modal length | ≥ 99% |
| Shape | share with the modal character-class shape | ≥ 99% |
| Distinctness within the part | distinct / non-null | ≥ 0.99 for a key; it may repeat in a referencing part |
| Leading zeros kept | stored as a string, and some values start with "0" | flag only |
| Check-digit family | pass rate for each family below | ≥ 99% **and** ≥ 5× the chance rate |
| Surrogate-like | integer, and max − min + 1 ≈ count (a dense sequence) | marks a *local surrogate*, not an issued identifier |
| Issuer | the same values appear in an independent source (cross-source overlap ≥ 0.9) | evidence for "authoritative or proxy" [S1]; otherwise the issuer is "unknown" |

**Check-digit families.** These are algorithms from source code [S5], not lists of known identifiers:

| Family | Rule (python-stdnum) | Chance pass rate |
|---|---|---|
| ISO 7064 mod 97-10 | map each character from base 36 to decimal digits; valid if the whole integer mod 97 = 1; two check digits | ~1/97 |
| ISO 7064 mod 11-2 | `check = (2*check + v) % 11` over the digits ('X' = 10); valid if 1 | ~1/11 |
| ISO 7064 mod 11-10 / mod 37-36 (pure system, mod *x*+1, *x*) | `check = ((check or m)*2 % (m+1) + v) % m`; valid if 1 | ~1/10, ~1/36 |
| Luhn (mod 10, also mod *N*) | double every second digit from the right, sum the digit sums; valid if the sum mod *n* = 0 | ~1/10 |
| Verhoeff, Damm | table-driven mod 10 | ~1/10 |
| Weighted mod 10 / mod 11 (e.g. weights 3-1, or 2…7) | **Proposal:** search small weight vectors and report the best one, not a named scheme | ~1/10, ~1/11 |

- Chance rates are arithmetic: one check symbol over *m* symbols passes by chance about 1/*m* of the time.
- **A pass rate only counts when compared with its chance rate.** 12% of values passing Luhn is noise; 99.8% is a strong signal.

## 3. Key discovery: unique column combinations, inclusion dependencies, foreign-key scoring, link tables

| Work | What it gives us | Source |
|---|---|---|
| DUCC (Heise et al., PVLDB 7(4) 2013) | Finding all minimal unique column combinations is "a NP-hard problem"; the search space is exponential in the number of columns; a hybrid depth-first and random-walk lattice traversal | [S7] |
| HyUCC (Papenbrock & Naumann, BTW 2017) | Earlier algorithms are "inapplicable" beyond about 50 columns × 1 million rows; HyUCC samples, then validates | [S8] |
| SPIDER (Bauckmann et al., ICDE 2007) | Sort and deduplicate every column, then test all pairs in one pass; an extension finds partial and composite inclusion dependencies | [S9] (excerpt) |
| BINDER (Papenbrock et al., PVLDB 8(7) 2015) | Divide and conquer for unary and n-ary inclusion dependencies, larger than memory | [S10] |
| MANY (Tschirschnitz et al., TODS 42(3) 2017) | Bloom filters for very many small tables | [S11] |
| Metanome | Java implementations of all of the above | [S14] |
| Rostin et al. 2009 rules, as listed by Zhang | (1) the foreign key has significant cardinality; (2) good coverage of the primary key; (3) it is not the primary key for too many foreign keys; (4) it is not a subset of too many primary keys; (5) similar value lengths; (6) few primary-key values outside the foreign key's range; (7) similar column names | [S12] |
| Zhang et al., PVLDB 3(1) 2010 | Partial inclusion σ(F,P) = \|F∩P\|/\|F\| ≥ θ, with θ = 0.9; **Randomness**: a real foreign key is a near-uniform sample of the primary key's ordered values, measured by Earth Mover's Distance; values are ordered numerically or lexically; it also covers multi-column foreign keys | [S12] |

**Recommendation (Proposal).**
- Do not ship Metanome; it would be a Java dependency.
- Implement bounded versions in DuckDB SQL instead:
  - **Single-column keys:** exact `COUNT(DISTINCT c) = COUNT(*)` with no nulls.
  - **Composite keys:** a level-wise search up to **3 columns**. It only uses columns that are not near-constant and not free text, and it stops at the first minimal key found at each level. This keeps the search polynomial; DUCC [S7] shows the unbounded problem is NP-hard.
  - **Inclusion dependencies:** an anti-join count for each type-compatible pair, after pruning by shape and length. Report σ, and keep the pair if σ ≥ 0.9.
  - **Foreign-key score:** score each kept pair with Rostin rules 1, 2, 5, 6 and 7 plus Zhang's randomness. A simple version is the KS distance between the ranks of F and of P; EMD is the published measure.
  - **Uniqueness and inclusion must be exact.** Never use the approximate `approx_unique` from `SUMMARIZE` for them (section 14).
- **Link tables:** a part whose minimal key consists entirely of foreign keys to two or more parts (or two foreign keys to the same part, which is a self-link), with few other attributes. Its extra columns are typically a role or type code and dates. Classify it as a **relationship**.

## 4. Key design when no identifier exists

- Kimball: a warehouse should use its own "anonymous integer primary keys" rather than natural keys, because natural keys repeat over time and across sources [S15].
- A **durable key** stays the same while versions change [S15].

**Proposal.**
1. Prefer a **natural composite key** if one passes **stability tests**:
   - it is unique in every delivery seen;
   - no part of it is null;
   - **key persistence**: the same entity keeps the same key between deliveries, measured as the share of non-key attributes unchanged for matched keys;
   - none of its columns is a free-text label that gets edited.
2. If none passes, design a **surrogate** with a written rule. For example: sha256 of the normalized natural columns, or a sequence keyed by first appearance.
   - Record which columns feed it, and that it changes if they change.
3. The designed key becomes the **record key** (decision 6).
   - A surrogate is never sent to the cross-reference table, because it is local.

## 5. Time models

**Definitions** [S16].
- *Valid time* is "the time period during which a row is regarded as correctly reflecting reality". In SQL:2011 it is an **application-time period**, here called "as of".
- *Transaction time* is the period "during which a row is committed to or recorded in the database". In SQL:2011 these are **system-versioned** tables, here called "as at".

**Postgres support.**
- From **PG18**, `UNIQUE (id, valid_at WITHOUT OVERLAPS)` "behaves like `EXCLUDE USING GIST (id WITH =, valid_at WITH &&)`".
- Also from PG18, `PERIOD` foreign keys require the referent to cover the whole period [S17].
- The PG18 release notes list both features [S17]. The PG17 `CREATE TABLE` page has no `WITHOUT OVERLAPS`.
- On PG16, the same guarantee is an `EXCLUDE USING gist` constraint with `btree_gist`. `btree_gist` is offered by Snowflake Postgres [S48].

**Change-data shapes.**
- Debezium-style change feeds carry `op` (c, u, d, r for snapshot read, t), `before`, `after` and `source` [S18].
- Kimball separates **transaction** fact grain ("a measurement event at a point in space and time") from **periodic snapshot** grain ("the grain is the period") [S19].

**Detection rules (Proposal).**

| Finding | Test |
|---|---|
| Snapshot delivery | delivery N contains ≥ 98% of N−1's keys, and its row count ≈ the distinct keys |
| Changes only | key overlap between N and N−1 is under 20%; or a change-type column with 2–5 values such as I/U/D or c/u/d; or a delete flag |
| Versions per key | more than one row per business key with different timestamps; report the distribution (p50, p99) |
| Valid-time pair ("as of") | two date columns with start ≤ end in ≥ 99% of rows, open-ended values (null or far-future), and no overlap per key |
| Record-time column ("as at") | a timestamp unrelated to the business date, close to the delivery date, monotonic with the load order |
| Event time | one timestamp per row, in a transaction-like part (section 1.2) |
| Time series | (entity key, timestamp) is unique, a numeric measure is present, and the modal step between timestamps covers ≥ 90% of steps; report the step, gaps and duplicates |
| Refresh rate | the modal gap between deliveries' record times |

## 6. Sensitive data detection and masking

**Presidio** tags entities by pattern match combined with a checksum or validator and with context words.
- Examples: CREDIT_CARD "pattern match and checksum"; IBAN "pattern match, context and checksum"; EMAIL "RFC-822 validation"; PERSON and LOCATION by NER and context [S20].
- *Presidio Structured* tags a column by "most common" entity, "highest confidence", or a mixed threshold, then anonymizes the column [S20].

**Google Sensitive Data Protection** reports five likelihoods, from VERY_UNLIKELY to VERY_LIKELY. "Passing checksums" and "strong contextual clues" raise likelihood [S21].

TestGen already flags "Potential PII" as a hygiene likelihood (DQ note, section 1.1).

**GDPR Article 9 special categories** [S22]: racial or ethnic origin, political opinions, religious or philosophical beliefs, trade-union membership, genetic data, biometric data for unique identification, health data, and sex life or sexual orientation.
- Government ID numbers and account numbers are **not** in Article 9.

**Proposal.** Tag each column personal, sensitive personal or none from four signals:
1. **name heuristics:** column-name tokens such as name, birth, email, phone, address, ssn, passport, gender or health;
2. **value detectors:** pattern + checksum (section 2) + validator;
3. a **column vote:** the share of sampled non-null values matching (≥ 50% LIKELY);
4. **context:** a person-like part, i.e. a master with name and birth-date columns.

Masking:
- Samples written to REPORT.md or findings.yaml keep **shape only**: `Aaaa A. Aaaaa`, `999-99-9999`.
- Optionally a salted hash prefix, so two samples can be compared without revealing values.
- Raw values never leave the transient DuckDB session.

## 7. Drift between deliveries

**Tools:**
- **Soda schema checks** warn when a column is added, removed, moved or retyped; they need two scans to produce a result. Its **distribution check** offers KS (continuous), chi-square (categorical), PSI, Standardized Wasserstein and Standardized EMD against a stored reference distribution [S24] (excerpt).
- **Great Expectations** `expect_column_kl_divergence_to_be_less_than` compares a column with a stored partition object. Without `tail_weight_holdout`, an unseen value drives KL "to +Infinity" [S25].
- **Deequ** stores metrics in a repository and runs anomaly strategies such as `RelativeRateOfChangeStrategy` [S23].

**Proposal for `compare`.** Store each delivery's profile in `findings.yaml` and diff it against the next delivery. Diff these items:
- **schema:** added, removed, renamed (same values under a new name) and retyped columns;
- **key health:** uniqueness, nulls, inclusion σ;
- **cardinality:** new or vanished codes in reference parts, which feed RDM review;
- **distributions:**
  - PSI over decile bins for numbers, flagged at > 0.2 (a common rule of thumb; unsourced);
  - chi-square or PSI over top-k plus "other" for categories;
- **volume:** rate of change, Deequ-style;
- **time model:** a snapshot becoming a delta, or a new date role.

Each drift item becomes a proposed change for refining-rules (decision 18).

## 8. Hierarchies: inference and storage

### 8.1 Inference (the four evidence kinds in decision 11)

1. **Parent column or self-link.** An inclusion dependency from a column to the same part's key (σ ≥ 0.9).
   - Walk it with `WITH RECURSIVE`, using `CYCLE … SET is_cycle` and `SEARCH DEPTH FIRST` (both added in PG14) [S26] to measure depth, find orphans and detect cycles.
2. **Functional dependencies.**
   - Full FD discovery does not scale: "None of the state-of-the-art algorithms … scales to datasets with hundreds of columns or millions of rows" [S13].
   - **Proposal:** test only pairwise A → B among low-cardinality categorical columns, for example with `COUNT(DISTINCT B) per A = 1`.
   - Accept the chain if it holds for ≥ 99% of rows, so it is "near-exact" per decision 11, and mark the violating rows.
   - A chain A → B → C with |A| > |B| > |C| is a level hierarchy.
3. **Code nesting.** Within one column (or across a pair of columns), a code's prefix of length *k* equals its parent's code in ≥ 99% of rows.
   - Report the segment lengths.
4. **Separate level tables.** A chain of parts each linked by a many-to-one foreign key, with descending cardinality, for example city → region → country.

### 8.2 Storage, compared for agents

| Model | Edit (move a subtree) | Ancestors | Subtree | Integrity | Read by an LLM | Portability |
|---|---|---|---|---|---|---|
| Adjacency list (parent_code) | 1 row | recursive CTE [S26] | recursive CTE | foreign key on the parent | one hop per row; the agent must chase | any SQL |
| Materialized path (text) | rewrite every descendant | split the path | `LIKE 'a/b/%'` (btree with `text_pattern_ops`) | no foreign key; needs a check | **whole chain in one string** | any SQL |
| Closure table (ancestor, descendant, depth) | O(subtree × ancestors) rows | 1 indexed join | 1 indexed join | triggers or rebuild | pairs, poor | any SQL [S31] |
| Nested sets (lft, rgt) | renumber O(n) | range | range | fragile | opaque numbers | any SQL [S30] |
| `ltree` | rewrite every descendant | `@>` | `<@`, GiST-indexed | type-checked labels | readable (`Top.Science.Astronomy`) | Postgres only [S27] |

Constraints on `ltree` [S27]:
- labels are alphanumerics, `_` and `-` (the exact range depends on locale), at most 1,000 characters per label and 65,535 labels per path;
- it is a "trusted" extension;
- it is offered by Snowflake Postgres [S48].
- Raw codes containing `.`, `/` or spaces must be encoded first.

**SKOS** [S32]:
- `skos:broader` is the direct link and is **not** transitive;
- `skos:broaderTransitive` is the transitive closure, meant for inference;
- this maps exactly to parent link versus path.

**XKOS** [S33] adds the pieces we need for level metadata:
- `xkos:ClassificationLevel`, with `xkos:depth` ("1 for the highest level");
- `xkos:levels`;
- `xkos:Correspondence` / `ConceptAssociation` for crosswalks;
- `xkos:supersedes` (= `dcterms:replaces`) for versions.

**Recommendation.**
- Store **one parent link per node** in drafts.
- At **publish**, write `path` (text, delimiter-escaped codes), `level` and `depth` into the immutable published version.
- Because published versions never change, the costs of editing a path, closure table or nested set disappear on the read side. What remains is read cost and readability, and a text path wins both for an agent.
- Add `ltree` only as an optional RDM index for subtree queries. Keep it out of the spec format: decision 36 says the spec does not depend on the store, and silver may be Snowflake.

## 9. RDM practice, and reconciling with PR #815

**Standards.**
- *ISO/IEC 11179-3*: a code set is an *enumerated* value domain, where each permissible value maps to exactly one value meaning. A *described* value domain, such as "weight in kilograms", is a range, not a code set [S34].
  - This gives profiling a test: a reference part enumerates its values; a measure column describes a range.
- *SKOS*: a code set is a `ConceptScheme`. A code is a `Concept` with:
  - `skos:notation` (the code);
  - at most one `prefLabel` per language (S14);
  - `altLabel`s (synonyms);
  - `inScheme` and `topConceptOf` [S32].
- *Crosswalk match types* (SKOS mapping): `exactMatch` (transitive, a sub-property of `closeMatch`), `closeMatch` (not transitive), and `broadMatch`/`narrowMatch` [S32].
- *Versions*: XKOS `follows` and `supersedes` [S33].

**Tools.**

| Tool | Code sets and hierarchies | Crosswalks | Versions and approval | Source |
|---|---|---|---|---|
| Informatica Reference 360 | code lists, hierarchical code lists | "a one-way relationship between code values in a pair of code lists", with value mappings | stakeholders and workflow | [S35] (excerpt; the page returned 403) |
| Collibra | Code Set → Code Value; flat or hierarchical | a Crosswalk asset from a source code set to a target code set | Candidate → Approved, plus an optional custom "Published" status | [S36] (summary) |
| TIBCO EBX | datasets in *dataspaces* | — | child dataspaces branch, then merge after a reviewed diff; **snapshots are read-only** and never modified | [S37] (excerpt) |
| Semarchy xDM | reference entities in the model | — | frozen model *editions* deployed to a data location | [S38] (excerpt) |

All four tools share the same shape, and it matches decision 19:
- a draft that can be edited;
- review and approval;
- an immutable published version.

Add one thing to the plan: a **match type on each crosswalk row** (exact, close, broad, narrow). With it, an agent knows whether a mapped code is interchangeable.

**PR #815 reconciliation.** `crates/source-contract/src/reference.rs` freezes `read.references` inside the contract with these bounds:
- at most 16 tables;
- at most 10,000 keyed rows per table;
- 1–32 columns per row;
- at most 100,000 cells in total;
- names and keys of at most 128 bytes;
- cells of at most 4,096 bytes.

It also offers `lookup` with `on_missing: null|error`. Separately, the rules-YAML check `in_reference@1` already pins a reference file by `sha256` (`skills/data-onboarding/REFERENCE.md`).

**Proposal.**
- An RDM publish emits, for each code set, a canonical mapping that fits those bounds, plus its `{code_set, version, sha256}`.
- A contract embeds the rows **and** the pin. This is the pinned-snapshot idea; the reader does not change.
- Code sets above the bounds need a pin by reference, resolved from published silver at load. That is a later reader change, in Phase B.

## 10. Agent context design

**Context principles.**
- "Context … must be treated as a finite resource with diminishing marginal returns".
- Find "the smallest possible set of high-signal tokens".
- Prefer just-in-time loading through "lightweight identifiers" [S41].

**Tool principles.**
- Agents handle "natural language names … significantly more successfully than … cryptic identifiers".
- Paginate and truncate with sensible defaults; Claude Code caps tool output at 25,000 tokens.
- Offer a concise or detailed response format, and give actionable error messages [S42].

The plan's 8 KB bundle, roughly 2,000 tokens, fits well inside that cap.

**Self-describing views.** `COMMENT ON` stores one comment per object, takes `relation_name.column_name` for columns, and is dropped along with the object [S39].
- **Proposal:** 1a must confirm by test that column comments on *views* round-trip through `col_description`.

**Trust signals in every bundle (Proposal):**
- `source` and capture id (provenance);
- `version` and `sha256`;
- `valid_from` and `valid_to`;
- `status` (draft, approved or published), plus the approver and time;
- `as_of` (the time the answer refers to);
- `truncated: true` with a next-page token.
- Names come first; ids appear only next to names.

**Search** (decision 23).
- Postgres full-text search adds what `LIKE`/`ILIKE` lack: dictionaries, stemming, `websearch_to_tsquery`, and the `ts_rank` and `ts_rank_cd` ranking functions [S40].
- Index the labels, synonyms and definitions with `to_tsvector`. Use the `simple` configuration for codes.
- A fallback of `ILIKE '%x%'` is **not indexable by btree**. `pg_trgm` GIN indexes support `LIKE`, `ILIKE`, regular expressions and similarity (`%`, `<->`) [S28], and Snowflake Postgres offers it [S48].
  - **Recommend `pg_trgm` GIN** on labels and synonyms. It also gives tolerance for typos with no embeddings.
- `unaccent` is also offered [S48].

## 11. Unstructured extraction under the certainty rule

| Method | Certain? | Why |
|---|---|---|
| iXBRL tags | **yes**, given the tag | `ix:nonFraction` carries `contextRef`, `unitRef`, `decimals`, `scale` and `format` (a named transformation) [S43]. Hidden content must be handled; the repo already has `_strip_hidden_ixbrl_content` (CLAUDE.md, Ticket 101). |
| HTML tables | **grid: yes. Meaning: only with an exact header match or a cross-check** | The WHATWG "table processing model" builds the cell grid deterministically, including `rowspan` and `colspan` [S44]. Which field a header *means* is not stated by the markup. |
| Labelled sections (exact heading text, then value) | yes if the label set is fixed and matched exactly | deterministic string match |
| PDF, text layer, ruled tables | **candidate** unless cross-checked | Camelot `lattice` is "Deterministic; detects the grid from the ruled lines"; `stream` and `network` are whitespace heuristics [S45]. pdfplumber "works best on machine-generated, rather than scanned, PDFs" [S46]. |
| PDF, scanned or OCR or ML | **never certain** | Camelot `ml` with OCR is a neural model [S45]. Its accuracy metrics are scores, not proof. |
| Free text (NER, LLM) | never certain alone | accepted only through a cross-check with structured data (decision 27) |

**Proposal.** "Second, independent extraction" means two extractors with different methods agreeing on the value **and** the cell position. For example, pdfplumber's table finder and Camelot `lattice`. Two runs of one tool do not count.

## 12. Store-suggestion heuristics

**Evidence.** Stonebraker and Pavlo (2024) [S47] conclude that:
- the relational model with extensible types "has dominated all comers";
- graph workloads simulated on an RDBMS have outperformed graph DBMSs in studies, and SQL/PGQ (SQL:2023) narrows the gap further;
- column stores "have taken over the data warehouse marketplace".

This supports decision 25: no graph database.

**Mapping (Proposal, advisory only, per decision 1):**

| Finding | Suggested store |
|---|---|
| Master data: entity, identity, survivorship | MDM Postgres (an existing or new kind) |
| Reference data: code set, hierarchy, crosswalk | RDM Postgres → published to silver |
| A relationship between masters | MDM relationships (Postgres rows; recursive SQL with a hop limit) |
| Transaction/event, time series, append-heavy, wide scans | silver (columnar: Snowflake; for trials, local PG `silver`) |
| Irreducibly nested and schemaless | keep raw in bronze; parse the lists into child tables (decision 10) |
| Metadata (manifests, hashes, run ids) | Bookkeeping or the catalog, not a data store |

**Graph or document signals that still map to Postgres:**
- a relationship part whose traversal depth is greater than 3;
- many relationship types;
- objects with more than 200 fields where field appearance is under 10%. DuckDB's JSON reader switches to `MAP` at the same point [S50].

Report these as signals, not as store changes.

## 13. Snowflake-hosted Postgres

Verified from the raw HTML of the extensions page [S48]:

| Extension | Listed? |
|---|---|
| `ltree` | yes |
| `pg_trgm` | yes |
| `unaccent` | yes |
| `fuzzystrmatch` | yes |
| `btree_gist` | yes |
| `btree_gin` | yes |
| `citext` | yes |
| `tablefunc` | yes |
| `postgres_fdw` | yes |
| `vector` (pgvector) | yes; out of scope (no embeddings) |

- Extensions are enabled "by the admin user" with `CREATE EXTENSION` [S48].
- Full-text search (`tsvector`, `tsquery`) is core Postgres [S40]. It needs no extension.
- Postgres majors 16–18 are available [S49].
- **Unknown:** whether a custom synonym dictionary file (a `.syn` file in `$SHAREDIR`) can be installed. Store synonyms in a column instead.

## 14. DuckDB capabilities and limits

All from the DuckDB docs source, `docs/current` [S50]; DuckDB 1.5.6 was used locally.

- **CSV.**
  - `read_csv` runs a sniffer over a **sample of 20,480 rows** by default.
  - `sample_size = -1` reads the whole file.
  - `sniff_csv()` returns the detected dialect.
- **JSON and NDJSON.**
  - `read_json` with `format` set to auto, array, newline_delimited or unstructured.
  - The type-detection `sample_size` defaults to 20,480.
  - `maximum_object_size` defaults to 16 MB.
  - `map_inference_threshold` is 200, and `field_appearance_threshold` is 0.1, below which a `MAP` is inferred.
- **Parquet** is native.
- **Databases.**
  - `ATTACH '…' (TYPE postgres, READ_ONLY)` and `ATTACH 'x.db' (TYPE sqlite)`. `READ_ONLY` is a general `ATTACH` option (`sql/statements/attach.md`).
  - The connection string comes from an environment variable and is never echoed (decision 2).
- **Statistics.**
  - `SUMMARIZE` returns min, max, `approx_unique`, avg, std, q25, q50, q75, count and null_percentage. The docs note that "the quantiles and percentiles are **approximate**".
  - `approx_count_distinct` uses HyperLogLog. `approx_top_k` and `reservoir_quantile` also exist.
- **Sampling.**
  - `USING SAMPLE n ROWS` / `PERCENT` with `reservoir`, `bernoulli` or `system`, plus `REPEATABLE (seed)`.
  - `system` samples whole **vectors**, which biases clustered data. Use `reservoir` or `bernoulli`.
- **Limits.**
  - Core has **no XML and no zip reader**. The community extensions `webbed` (XML and HTML) and `zipfs` are MIT, but they are signed with the *community* key, not the core key. Core-only mode is `SET allow_community_extensions = false`.
  - **Proposal:** unzip and flatten XML with the Python standard library (`zipfile`, `xml.etree.ElementTree.iterparse`) into JSONL or Parquet, then profile that with DuckDB. This keeps decision 3's "never a platform dependency".

## 15. Trial B candidates

| | **Contoso V2** [S52] | **Wide World Importers** [S51] | **AdventureWorks** [S53] |
|---|---|---|---|
| Licence | MIT (generator and data repo) | MIT (sql-server-samples `license.txt`) | MIT (same repo; the Postgres port is MIT) |
| Formats | CSV, Parquet, Delta, SQL Server `.bak`; sizes 10k, 100k, 1M, 10M and 100M (csv-10k is 5.4 MB as 7z) | SQL Server `.bak` (127 MB) or `.bacpac` (61 MB) only; needs an MSSQL container to export | CSV in the OLTP install script (17 MB zip; unusual delimiters); a Postgres install script exists |
| Parts | 8 files: customer, product, store, date, currencyexchange, orders, orderrows, sales | 4 schemas, ~31 tables: People, Customers, Suppliers, StockItems, Orders/Lines, Invoices/Lines, Transactions, Cities → StateProvinces → Countries, code tables (DeliveryMethods, PaymentMethods, TransactionTypes, Colors, PackageTypes), categories, StockItemStockGroups (many-to-many), sensor readings | Person, Customer, Store, Product, SalesOrder, ProductCategory → Subcategory, CountryRegion, Currency, ShipMethod, Employee (hierarchyid) |
| Master | yes | yes | yes |
| Reference code lists | embedded in the masters (denormalized) plus ISO-style currency codes | separate tables | separate tables |
| Category hierarchy | yes, inside product | yes (stock groups, many-to-many) and geography level tables | yes, level tables |
| Hierarchy evidence kinds | functional dependency, code nesting | level tables | level tables, materialized path (hierarchyid) |
| Parent column or self-link | no | no | path only |
| Relationships | facts only | many-to-many link table | person ↔ business entity links |
| Time | date columns on several parts; a daily rate file | **system-versioned temporal tables** (as at) | ModifiedDate only |
| Personal data | generated names, addresses, birthdays, coordinates | names, phones, emails, logons | names, emails, phones |
| Memorization risk | low: generated rows; the schema is known to Power BI users | medium | **high**: a classic sample |
| Loading to SQLite/PG | DuckDB from CSV, trivially | via an MSSQL container, then export | Postgres script exists; CSV import needs dialect fixes |

**Recommendation.**
- Use **Contoso V2** (10k or 100k) as Trial B. It is open, non-financial in domain, unlikely to be memorized, and loads from both CSV and SQLite (built by DuckDB from the CSV).
- Its contents were checked locally: the 10k build's 8 CSV files load cleanly in DuckDB.
  - **Exact rules are withheld; only evidence kinds are listed.** Decision 35 says the answer key is written before the skill sees the data, and an agent in this repo could read this note.
- If a normalized, temporal database is wanted, add **WWI** as Trial B2. It is the only candidate with as-at history and separate level tables.
- **None of the three has a plain parent column.** Trial A's relationship data is the place to prove that evidence kind.
- Synthea (Apache-2.0, seedable, rich in personal data) [S54] was rejected because it has no in-data category hierarchy.

## 16. Recommendations and conflicts with the plan

### 16.1 Rules (all Proposals, for approval)

- **Class rules:** the table in section 1.2, with the thresholds in sections 2–5.
- **Sampling above 5 GB:**
  1. Read with `sample_size = -1` for types only if the time estimate allows. Otherwise use a seeded `reservoir` of min(1 million rows, 1%) with `REPEATABLE(seed)`.
  2. Run every candidate search on the sample. **A sample can disprove but never prove** uniqueness or an FD.
  3. Prove the survivors with full passes: exact `COUNT(DISTINCT)`, and anti-joins for inclusion.
     - For inclusion, sample the *dependent* side and scan the *referenced* side fully. Otherwise missing referents look like violations.
  4. State the estimated time before each full pass, from the bytes per second measured in step 1.
- **Hierarchy storage:** a parent link in drafts; at publish, a materialized text path, level and depth; optionally an `ltree` index in RDM only (section 8.2).

### 16.2 Plan decisions that the evidence contradicts or leaves unclear

1. **Decision 3 against decision 2: XML and zip.** DuckDB core cannot read them (section 14).
   - Amend decision 3: unpack and flatten with the Python standard library, then use DuckDB.
   - Do not rely on community extensions.
2. **Decision 21, "generated readable path".** A Postgres generated column "cannot … reference anything other than the current row" [S29].
   - The path must be computed when a version is published, or by a trigger.
   - Reword it to "a path, level and depth materialized at publish".
3. **Decision 36: PG16 against temporal keys.** `WITHOUT OVERLAPS` and `PERIOD` foreign keys need PG18 [S17]. Snowflake Postgres offers 16–18 [S49]. Choose one:
   - (a) run the sandbox on PG18; or
   - (b) stay on PG16 and use `EXCLUDE USING gist` with `btree_gist`.
4. **Decision 26: 500 pairs cannot show 99.5% precision.**
   - With 0 errors in 500 pairs, the exact one-sided 95% lower bound (Clopper–Pearson [S55]) is 0.05^(1/500) ≈ **99.40%**.
   - Showing ≥ 99.5% needs about **598 error-free pairs**: ln 0.05 / ln 0.995.
   - Either raise the count to about 600, or say that 99.5% is a point estimate.
5. **Decision 7: "full scan".** DuckDB's type detection samples 20,480 rows by default, and `SUMMARIZE` is approximate.
   - "Full scan" must mean `sample_size = -1` plus exact counts for every test.
6. **Decision 8: "sensitive personal" is undefined.**
   - GDPR Article 9 [S22] excludes ID and account numbers.
   - DLP tools treat those numbers as sensitive [S20, S21].
   - The operator should pick the definition.
7. **Decision 28: Trial B as a SQLite or Postgres database.** None of the candidates ships SQLite, and WWI needs an MSSQL export.
   - Building the SQLite file from the CSV with DuckDB satisfies the decision.
   - Trial B cannot cover the parent-column evidence kind (section 15).
8. **Decision 11: functional dependencies.** This is feasible only in the bounded, pairwise form (section 8.1). Full FD discovery is not feasible [S13].
9. **The brief named "decisions 1–49", but the plan has 38.** Both `.scratch/profiling/plan.md` and `~/.claude/plans/shiny-hopping-scone.md` have 38. This note uses 1–38.

## Sources

Repository: `crates/source-contract/src/reference.rs`; `skills/data-onboarding/REFERENCE.md` (`in_reference@1`); `edgar_warehouse/mdm/clean/relationships.py` (`CONTRACTS`, `HIERARCHIES`); `.scratch/data-quality/research/01-datakitchen-testgen-observability.md`; `rules/reference/sec-place-codes.yaml`.

- S1 ISO 8000-2:2020 preview (clauses 3.2.5, 3.3.1, 3.3.6, 3.3.8): https://cdn.standards.iteh.ai/samples/80543/52a2903758024943b67d346ffb2a64bc/ISO-8000-2-2020.pdf
- S2 ISO/DIS 8000-200 (excerpt): https://www.iso.org/standard/90857.html
- S3 ISO/IEC 25024 master-data definition, as quoted in Informatica (IOS Press) (excerpt): https://content.iospress.com/articles/informatica/infor534
- S4 DAMA DMBOK2 overview: https://www.dama-dk.org/onewebmedia/DAMA%20DMBOK2_PDF.pdf
- S5 python-stdnum source (`iso7064/`, `luhn.py`, `verhoeff.py`, `damm.py`): https://github.com/arthurdejong/python-stdnum/tree/master/stdnum
- S7 Heise et al., DUCC, PVLDB 7(4) 2013: https://www.vldb.org/pvldb/vol7/p301-heise.pdf
- S8 Papenbrock & Naumann, HyUCC, BTW 2017: https://hpi.de/fileadmin/user_upload/fachgebiete/naumann/publications/2017/paper.pdf
- S9 SPIDER project page (excerpt): https://hpi.de/naumann/projects/completed-projects/spider-data-profiling.html
- S10 Papenbrock et al., BINDER, PVLDB 8(7) 2015: http://www.vldb.org/pvldb/vol8/p774-papenbrock.pdf
- S11 Tschirschnitz et al., MANY, TODS 2017: https://hpi.de/oldsite/fileadmin/user_upload/fachgebiete/naumann/publications/PDFs/2017_tschirschnitz_detecting.pdf
- S12 Zhang et al., "On Multi-Column Foreign Key Discovery", PVLDB 3(1) 2010 (lists the Rostin et al. 2009 rules): https://vldb.org/pvldb/vol3/R72.pdf
- S13 Papenbrock et al., "Functional Dependency Discovery: An Experimental Evaluation of Seven Algorithms", PVLDB 8(10) 2015: http://www.vldb.org/pvldb/vol8/p1082-papenbrock.pdf
- S14 Metanome algorithms: https://github.com/HPI-Information-Systems/metanome-algorithms
- S15 Kimball, surrogate and durable keys: https://www.kimballgroup.com/data-warehouse-business-intelligence-resources/kimball-techniques/dimensional-modeling-techniques/dimension-surrogate-key/ and …/natural-durable-supernatural-key/
- S16 Kulkarni & Michels, "Temporal features in SQL:2011", SIGMOD Record 2012: https://sigmodrecord.org/publications/sigmodRecord/1209/pdfs/07.industry.kulkarni.pdf
- S17 PostgreSQL 18 `CREATE TABLE`: https://www.postgresql.org/docs/18/sql-createtable.html ; release notes: https://www.postgresql.org/docs/18/release-18.html
- S18 Debezium PostgreSQL connector, event values: https://debezium.io/documentation/reference/stable/connectors/postgresql.html
- S19 Kimball, transaction and periodic snapshot fact tables: https://www.kimballgroup.com/data-warehouse-business-intelligence-resources/kimball-techniques/dimensional-modeling-techniques/transaction-fact-table/ and …/periodic-snapshot-fact-table/
- S20 Presidio supported entities and Presidio Structured (summary): https://presidio.dataprivacystack.org/supported_entities/ and https://presidio.dataprivacystack.org/structured/
- S21 Google Sensitive Data Protection, likelihood (summary): https://docs.cloud.google.com/sensitive-data-protection/docs/likelihood
- S22 GDPR Article 9(1), read from a mirror; official text: https://eur-lex.europa.eu/eli/reg/2016/679/oj ; mirror: https://gdpr-info.eu/art-9-gdpr/
- S23 Deequ README, profiling and anomaly examples: https://github.com/awslabs/deequ
- S24 Soda schema checks and distribution checks (excerpt): https://docs.soda.io/soda-documentation/soda-v3/sodacl-reference/schema and …/distribution
- S25 Great Expectations, KL-divergence expectation source: https://github.com/great-expectations/great_expectations/blob/develop/great_expectations/expectations/core/expect_column_kl_divergence_to_be_less_than.py
- S26 PostgreSQL `WITH` queries (SEARCH and CYCLE): https://www.postgresql.org/docs/current/queries-with.html ; PG14 release notes: https://www.postgresql.org/docs/release/14.0/
- S27 PostgreSQL `ltree`: https://www.postgresql.org/docs/current/ltree.html
- S28 PostgreSQL `pg_trgm`: https://www.postgresql.org/docs/current/pgtrgm.html
- S29 PostgreSQL generated columns: https://www.postgresql.org/docs/current/ddl-generated-columns.html
- S30 J. Celko, *Trees and Hierarchies in SQL for Smarties*, 2nd ed. (book, not read online; the nested-set model)
- S31 B. Karwin, *SQL Antipatterns*, ch. "Naive Trees" (book, not read online; the closure table)
- S32 W3C SKOS Reference (summary checked against section numbers): https://www.w3.org/TR/skos-reference/
- S33 XKOS vocabulary source: https://github.com/linked-statistics/xkos/blob/master/xkos.ttl
- S34 ISO/IEC 11179-3:2013/Amd 1:2020 preview (clause 3.2.96): https://cdn.standards.iteh.ai/samples/76748/c21178f082e148c2856bef3ce34bcf2e/ISO-IEC-11179-3-2013-Amd-1-2020.pdf
- S35 Informatica Reference 360, crosswalks (excerpt; 403): https://docs.informatica.com/master-data-management-cloud/reference-360-saas/current-version/reference-360/introducing-reference-360/key-concepts/crosswalks.html
- S36 Collibra reference data lifecycle (summary): https://productresources.collibra.com/docs/collibra/2021.09/Content/ReferenceData/co_reference-data-lifecycle.htm
- S37 TIBCO EBX dataspaces (excerpt): https://docs.tibco.com/pub/ebx/latest/doc/html/en/user_dataspace/userdataspace_intro.html
- S38 Semarchy xDM model editions (excerpt): https://www.semarchy.com/doc/semarchy-xdm/xdm/latest/Manage/models/overview.html
- S39 PostgreSQL `COMMENT`: https://www.postgresql.org/docs/current/sql-comment.html
- S40 PostgreSQL full-text search: https://www.postgresql.org/docs/current/textsearch-intro.html and …/textsearch-controls.html
- S41 Anthropic, "Effective context engineering for AI agents": https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- S42 Anthropic, "Writing effective tools for agents": https://www.anthropic.com/engineering/writing-tools-for-agents
- S43 Inline XBRL 1.1 Part 1: https://www.xbrl.org/specification/inlinexbrl-part1/rec-2013-11-18/inlinexbrl-part1-rec-2013-11-18.html
- S44 WHATWG HTML, table processing model: https://html.spec.whatwg.org/multipage/tables.html#table-processing-model
- S45 Camelot README: https://github.com/camelot-dev/camelot
- S46 pdfplumber README: https://github.com/jsvine/pdfplumber
- S47 Stonebraker & Pavlo, "What Goes Around Comes Around… And Around…", SIGMOD Record 53(2) 2024: https://db.cs.cmu.edu/papers/2024/whatgoesaround-sigmodrec2024.pdf
- S48 Snowflake Postgres extensions (raw HTML checked): https://docs.snowflake.com/en/user-guide/snowflake-postgres/postgres-extensions
- S49 Snowflake Postgres overview (versions 16–18): https://docs.snowflake.com/en/user-guide/snowflake-postgres/about
- S50 DuckDB docs source (`docs/current/`: `data/csv/auto_detection.md`, `data/json/loading_json.md`, `core_extensions/postgres/overview.md`, `core_extensions/sqlite.md`, `guides/meta/summarize.md`, `sql/functions/aggregates.md`, `sql/samples.md`, `operations_manual/securing_duckdb/securing_extensions.md`): https://github.com/duckdb/duckdb-web/tree/main/docs/current ; community extensions: https://github.com/duckdb/community-extensions/tree/main/extensions
- S51 Wide World Importers catalog: https://learn.microsoft.com/en-us/sql/samples/wide-world-importers-oltp-database-catalog ; licence: https://github.com/microsoft/sql-server-samples/blob/master/license.txt
- S52 Contoso Data Generator V2 (MIT): https://github.com/sql-bi/Contoso-Data-Generator-V2 ; data releases: https://github.com/sql-bi/Contoso-Data-Generator-V2-Data/releases
- S53 AdventureWorks for Postgres (MIT): https://github.com/lorint/AdventureWorks-for-Postgres ; OLTP script: https://github.com/Microsoft/sql-server-samples/releases/tag/adventureworks
- S54 Synthea (Apache-2.0) and its CSV data dictionary: https://github.com/synthetichealth/synthea and https://github.com/synthetichealth/synthea/wiki/CSV-File-Data-Dictionary
- S55 Clopper & Pearson (1934), *Biometrika* 26(4):404, doi:10.1093/biomet/26.4.404 (the formula; the arithmetic is computed in this note)

## Operator rulings on this note (2026-10-05 06:45 ET)

| Point | Ruling |
|---|---|
| XML and zip | Unpacked and flattened with the Python standard library, then profiled with DuckDB (Claude, from the evidence). |
| Hierarchy path | Computed at publish time and stored on each immutable version, not a Postgres generated column (Claude, from the evidence). |
| Temporal keys | The sandbox stays on PG16 with `EXCLUDE USING gist` + `btree_gist`; PG18 temporal keys are a later option (Claude, from the evidence). |
| Full scan | `sample_size=-1` for type detection and exact counts, never DuckDB's approximate summaries (Claude, from the evidence). |
| Functional dependencies | Bounded, pairwise checks only (Claude, from the evidence). |
| Name-match proof | Operator: "Raise to 600 pairs, lower bound ≥ 99.5%". At least 600 labelled pairs per rule; the 95% lower confidence bound on precision must be at least 99.5%. |
| Sensitive personal | Operator: "GDPR Art. 9 + government IDs + financial accounts". Sensitive personal = Article 9 categories, government-issued personal IDs, financial account and card numbers; personal = any other field that identifies a person. Both are masked. |
| Trial B | Operator: "Contoso V2". Its answer key is written before the skill sees the data. |
