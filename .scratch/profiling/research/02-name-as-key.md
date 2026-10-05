# A name as the only unique column: how to design the record key

Ticket: profiling research follow-up to [01 Research note](01-classify-and-profile.md) section 4.
Written on 2026-10-05 (ET) on branch `claude/profiling-01b-data-profiling-skill`. No request was made to sec.gov.

**How to read the citations.** Same style as note 01.
- `[Nn]` points to the source list at the end.
- **(excerpt)** means the claim came from a search-result excerpt or a summary, because the page blocked automated reading.
- Rules marked **Proposal** are this note's own suggestions for the operator to approve or change.

## Summary

1. **A name is not identity.** It changes on a rename, it arrives in variants (case, spaces, punctuation, Unicode form, spelling), different things share it (homonyms), and it can be reused (§1).
2. **A hash fixes the form of the key but not its meaning** (§2).
   - It gives a key of fixed length and the same value everywhere, with no lookup table.
   - It is only as stable as the normalized name. A rename makes a new key, and homonyms collide by design.
   - The normalization rule, not the hash, decides which variants merge.
3. **Normalize once, in Python, and store the result** (§2.2).
   - The rule is NFKC, then Unicode case folding, then whitespace cleanup, and it names its Unicode version.
   - The engines differ: DuckDB has no NFKC and no casefold, and Postgres has `casefold` only from version 18. So the key must be hashed from the stored string, never re-normalized in SQL.
4. **Use SHA-256 hex, never less than 128 bits** (§2.3).
   - DuckDB `hash()` may change between versions and is 64-bit, so it is out.
   - UUIDv5 (122 free bits) is the option when the column must be a `uuid`.
5. **The key is designed, never found** (§3, §4).
   - Test the name for uniqueness after normalization, for folded collisions, and for persistence over two deliveries. Until a second delivery exists, the key is provisional.
   - `name_hash` is right when a renamed record is a new record. A durable surrogate in a key map, looked up by the name hash, is right when a renamed record is the same one. The surrogate is also the default when the operator does not answer.
   - In MDM, the name is a match attribute.

---

## 1. Risks of a name as a key

A name is a label someone writes and edits. A key must not change while the thing it names lives on. Five ways a name breaks that:

1. **Renames.** The thing stays the same and its name changes. Kimball's general point holds here: keys from a source "are subject to business rules outside the control of the DW/BI system", and a natural key can change while the thing it names lives on [N5]. A name changes far more often than an issued number does.
2. **Variants of one name.** The same name can arrive spelled differently:
   - case (`Acme Holdings` / `ACME HOLDINGS`);
   - spacing (double spaces, leading or trailing blanks, no-break space);
   - punctuation (`Acme, Inc.` / `Acme Inc`);
   - Unicode form: a precomposed `é` versus `e` plus a combining accent, or full-width letters and ligatures. These are canonical or compatibility equivalents [N2];
   - abbreviation and spelling (`Intl` / `International`, `Corp` / `Corporation`, typos).
   Each variant is a different string, so a key made from the raw string splits one thing into several records.
3. **Homonyms.** Two different things can carry the same name. Any key made only from the name merges them.
4. **Reuse.** A name that one thing gave up can later be taken by another thing. That is a homonym spread over time, and only a second delivery can show it.
5. **Length and content.** Long free text makes a costly index and join column, and it often holds personal or sensitive words. Note 01's sensitivity rules then apply to the key itself.

This is why the profiler's `_candidates` skips any column averaging more than 2 words (`tokens <= 2.0`). It is also why note 01 §4 stability test 4 rules out "a free-text label that gets edited". A unique long name therefore never becomes a found key today. Instead, `choose_record_key` falls through to the durable first-appearance surrogate.

## 2. Hashing the name

### 2.1 What a hash fixes

- **Fixed length.** SHA-256 always produces a 256-bit digest (64 hex characters), however long the name is [N4].
- **Deterministic.** The same input always gives the same digest. RFC 9562 says this of name-based UUIDs: values made "from the same name (using the same canonical format) in the same namespace MUST be equal" (§6.5) [N1].
- **No lookup table.** Any process can compute the key on its own, with no shared sequence or key map. Practitioner accounts give this as the reason Data Vault 2.0 hashes its business keys: parallel loads compute keys without coordination [N7 (excerpt)].
- **Same value across systems, if the input bytes are the same.** Postgres `sha256(bytea)` returns `bytea` [N8]. DuckDB `sha256(value)` returns a lowercase hex `VARCHAR` [N9]. Both hash bytes, so they agree only when:
  - both hash the same UTF-8 bytes;
  - the Postgres side converts to hex: `encode(sha256(convert_to(s, 'UTF8')), 'hex')`.
  - Checked in this note (DuckDB 1.5.2, Python 3.12 `hashlib`): DuckDB `sha256('abc')` and `hashlib.sha256(b'abc')` both give `ba7816bf…15ad`, the value in the Postgres docs' example [N8]. For the non-ASCII string `Zürich Société` (NFC), DuckDB's digest equals `hashlib` over its UTF-8 bytes.

### 2.2 What a hash does not fix

A hash adds no identity. It only shortens the string it is given, so every risk in §1 that lives in the name passes straight through:

- **It is only as stable as the normalized name.** A rename makes a new key. The old key is orphaned, and nothing links the two.
- **Normalization decides which variants merge.** That choice is the real design decision. The hash only records it.
- **Homonyms collide by design.** Two things with the same normalized name get the same key. This is not a hash collision, so no hash length fixes it.
- **Reuse cannot be seen.** A name taken over by a new thing keeps the old key.

**The engines do not normalize alike.** This is the main practical finding:

| Step | Unicode Standard | Postgres 16/17 | Postgres 18 | DuckDB |
|---|---|---|---|---|
| Compatibility normalization (NFKC) | UAX #15 [N2] | `normalize(text, NFKC)` [N8] | same | none; only `nfc_normalize` [N9] |
| Case folding | `toCasefold`, D144–D147 [N3] | none (`casefold` absent from the 16 and 17 docs; checked 2026-10-05) | `casefold(text)`, collation-dependent [N8] | none; only `lower` [N9] |
| Lower case | — | `lower()`, "according to the rules of the database's locale" [N8] | same | `lower` |

So "compute the key in SQL wherever the data is" would give different keys in different engines and locales.

**Proposal.** Normalize once, in the profiler's Python. Store the normalized string next to the key. Every engine hashes that stored string, and none re-normalizes.

**Normalization standard.** The Unicode Standard defines an *identifier caseless match* as `toNFKC_Casefold(NFD(X)) = toNFKC_Casefold(NFD(Y))` (D147). It defines the *compatibility caseless match* as `NFKD(toCasefold(NFKD(toCasefold(NFD(X)))))` (D146), which takes an extra fold cycle because NFKD can produce new letters that must be folded again [N3].

- NFKC folds font variants, ligatures, full-width forms, superscripts and fractions [N2].
- Normalization itself does not change case [N2]. That is why folding is a separate step.
- Normalized text stays normalized under later Unicode versions only for characters assigned at the time [N2]. So the rule must name the Unicode version.

**Proposal.** The normalization rule, version `name_norm@1`:

1. Apply NFKC, then Unicode full case folding, then NFKC again (Python `unicodedata.normalize('NFKC', …)` and `str.casefold()`). This approximates D147's `toNFKC_Casefold`, but is not identical to it. Record the Python Unicode version (`unicodedata.unidata_version`). The version differs between machines: on 2026-10-05 the repo's `uv` Python 3.12 reported 15.0.0, while the system `python3` reported 13.0.0. So the rule **pins one `unidata_version`**, and a loader running a different version stops instead of minting keys. Normalizing "once" still happens again on every delivery, by whichever Python the loader runs.
2. Map every Unicode whitespace run to one ASCII space, and trim.
3. Optional and operator-chosen, never on by default:
   - strip punctuation;
   - strip accents;
   - drop legal-form words (`inc`, `ltd`, …).
   Each of these merges more variants and more homonyms.

Steps 1–2 only remove differences in how a name is encoded. Step 3 changes what counts as the same name, and that belongs to matching (§4.4).

### 2.3 Hash choice, length and collision odds

For n distinct names and a b-bit digest, the birthday bound gives the chance of at least one accidental collision:

p ≈ 1 − exp(−n² / 2^(b+1))

(computed in this note):

| Digest | free bits b | n = 10⁵ | n = 10⁶ | n = 10⁸ |
|---|---|---|---|---|
| 32-bit | 32 | 0.69 | ≈1 | ≈1 |
| 64-bit (DuckDB `hash`) | 64 | 2.7 × 10⁻¹⁰ | 2.7 × 10⁻⁸ | 2.7 × 10⁻⁴ |
| UUIDv5 | 122 | 9.4 × 10⁻²⁸ | 9.4 × 10⁻²⁶ | 9.4 × 10⁻²² |
| MD5 / SHA-256 truncated to 128 | 128 | 1.5 × 10⁻²⁹ | 1.5 × 10⁻²⁷ | 1.5 × 10⁻²³ |
| SHA-256 | 256 | 4.3 × 10⁻⁶⁸ | 4.3 × 10⁻⁶⁶ | 4.3 × 10⁻⁶² |

How each choice fares:

- **DuckDB `hash()` is ruled out.** Its documentation says "the used hash function may change across DuckDB versions" and "this is not a cryptographic hash" [N9]. A key must not change when the engine is upgraded, and 64 bits is weak at 10⁸ names.
- **SHA-256 (FIPS 180-4) [N4]** is the default. It is in both engines (Postgres `sha256` [N8], DuckDB `sha256` [N9]), and FIPS 180-4 calls it "computationally infeasible … to find two different messages that produce the same message digest" [N4].
  - If a shorter key is wanted, FIPS 180-4 §7 allows truncation "by selecting an appropriate number of the leftmost bits". It points to SP 800-107 (referenced, not read) for how to choose the length [N4].
  - **Proposal:** never fewer than 128 bits (32 hex characters).
- **MD5** is in both engines [N8, N9]. Its 128 bits are enough against accidental collisions. Its drawback is that collisions can be constructed on purpose. The `uuid-ossp` docs prefer v5 because "SHA-1 is thought to be more secure than MD5" [N8]. Prefer SHA-256, which has no such known attack.
- **UUIDv5 (RFC 9562 §5.5) [N1]** is SHA-1 over a namespace UUID followed by the canonical name bytes, kept to the leftmost 128 bits. The version and variant bits then overwrite 6 of those bits, leaving 122 free.
  - It suits a `uuid` column. RFC 9562 says v5 "SHOULD be used in lieu of UUIDv3".
  - Postgres has it only through the `uuid-ossp` extension, as `uuid_generate_v5(namespace, name)` [N8].
  - DuckDB has no v5 function, only `uuid()`/`gen_random_uuid()` (v4) and `uuidv7()` [N9].
  - The **namespace UUID is part of the rule.** One namespace per data set and part keeps equal names in different parts apart. RFC 9562 §6.5 says different namespaces give different UUIDs "with very high probability" [N1].
  - **Same standard as MD5:** SHA-1 collisions can also be constructed on purpose. RFC 9562 §8 points to RFC 6194 for its security [N1]. Against accidental collisions both are fine. Against someone who controls the names and wants two records to share a key, neither is, and only SHA-256 is.

**Proposal.** Use `sha256` hex of the stored normalized name, prefixed by the part name so equal names in two parts stay apart: `sha256(part || 0x1F || normalized_name)`, with a unit-separator byte as delimiter. Offer UUIDv5 only when the target column must be a `uuid`.

## 3. Tests from the data

All tests are exact counts on a full scan. Note 01's ruling is `sample_size=-1` and no approximate summaries, so a sampled part must read the name column in full first. This is what `confirm_sampled` does today for identifier-shaped columns. The tests below are **Proposals**.

1. **Unique after normalization** (`unique_after_normalization`).
   - Measure: the count of distinct `name_norm@1(name)` values equals the row count, and no row has an empty name.
   - Also report `unique_raw`. A name that is unique raw but not after normalization shows the source holds variant duplicates. Those are a quality finding, not a key.
2. **Folded collisions** (`folded_collisions`).
   - Measure: the groups of distinct raw names that become one normalized name. Report the number of groups and up to 5 masked examples.
   - Then run the stronger, optional step-3 folds (punctuation, accents, legal-form words) as a probe only. Count how many *more* groups they would create. This is `near_duplicates`.
   - Many near-duplicates mean the names are noisy. The data then needs matching (§4.4), not a key.
   - This probe uses the same exact-equality machinery. Fuzzy similarity, for example `pg_trgm` [note 01 S28], is a matching tool and is not run here.
3. **Persistence** (`persistence`).
   - This needs two deliveries. findings.md §3.1 keeps `persistence` null until `compare` sees a second delivery. So **any name-based key from one delivery is provisional.**
   - Measured by `compare`:
     - **kept:** the share of the earlier normalized names still present;
     - **renamed suspects:** rows that disappeared and appeared with the same non-name attributes. A rename makes a new key, and these pairs show how often that happens;
     - **reused suspects:** names present in both deliveries whose non-name attributes changed beyond the part's normal drift.
   - Persistence is the share of matched names whose other attributes are unchanged, the same measure note 01 §4 uses for natural keys.
4. **Shape guard.**
   - Measure: the name column's length profile (p50, p99, max) and its `sensitivity`.
   - A name that is personal or sensitive personal is not used as a key, hashed or not. A hash of a low-entropy personal value can be reversed by guessing.

**What "unique" can prove.** The tests can prove that names are unique in the deliveries seen. They cannot prove that two rows with the same name are the same thing, or that one renamed thing is still that thing. Only outside knowledge settles that, which is why §4 asks the operator one question.

## 4. Recommendation for the skill

Everything in this section is a **Proposal**.

### 4.1 When a normalized name counts as "found"

A name is never a found key. It is always a designed key, so `found: false`.

The profiler may report a normalized name as the **basis** of a designed key only when **all** of these hold:

- no other unique key exists in 1–3 columns (today's `unique_keys`), and no parent key plus a within-parent column exists;
- `unique_after_normalization` is true and the name has no null or empty rows, on a full scan;
- `folded_collisions` is not a separate condition: uniqueness after normalization already makes it 0. When the uniqueness test fails, `folded_collisions` explains why: raw variants that fold together are duplicates to resolve first, not a key;
- the name is not personal or sensitive personal (§3, test 4).

Note 01 §4 stability test 4 is kept. It rejects a free-text label as a *natural* key, and that still holds. This note only adds a *designed* key derived from the name, so the gap between a found key and a designed one stays visible.

`_candidates` stays as it is. A separate step, `name_basis`, looks at the single text column over 2 words that is fully filled and unique. It runs only when `unique_keys` returns nothing.

### 4.2 Hash of the normalized name, or a durable surrogate in a key map

Both designs fail on homonyms alike:

- A key map that looks up records by normalized name merges two things with one name, exactly as the hash does.
- A new homonym in a later delivery silently joins the existing record in both designs.

What differs is what happens on a rename or a variant:

| | `name_hash` | `surrogate` (key map, today's default) |
|---|---|---|
| Computed by | anyone, anywhere, from the stored normalized name | the profiler's loader only, which reads and writes the key map |
| Lookup table | none | a key map: `record_id`, `name_norm`, `name_hash`, first seen, aliases |
| Rename | becomes a new key; the old one is orphaned | the operator can point the new name at the old `record_id` as an alias, so identity survives |
| Variant found later | becomes a new key | the operator adds an alias |
| Homonym | merged | merged until the operator splits it; the key map can then hold two ids for one name, with a disambiguating rule |
| Kimball fit | — | matches Kimball's durable key: "persistent and does not change", "simple integers assigned in sequence" [N5, N6] |

**Choose `name_hash`** when the operator answers that a renamed thing is a *new* record (§4.5), and the data agrees:

- `folded_collisions` = 0;
- once a second delivery exists, persistence is high and there are no renamed suspects;
- other systems must compute the key without access to the key map.

This typically fits code lists and catalogues whose label is the value itself.

**Choose `surrogate`** in every other case:

- the operator answers that a renamed thing is the *same* record;
- homonyms are possible;
- persistence is low or unknown.

This is also the default when the operator does not answer. It is what `choose_record_key` already designs.

In the surrogate design, the name hash still has a job: it is the key map's **lookup column**. A row arrives, the loader computes `name_hash`, looks up `record_id`, and mints a new one on a miss. A renamed row therefore gets a new `record_id` before the operator can act. Hold the renamed suspects that `compare` finds for review. When the operator confirms a rename, the newly minted id is retired into an alias of the old one. So the operator's hash idea is used either way. The difference is whether the hash *is* the key or *finds* the key.

### 4.3 findings.yaml fields

findings.md §3 `record_key` today has `columns`, `found`, `design` (`natural_composite|surrogate|null`), `rule` and `evidence: {unique, null_rows, persistence}`.

**Proposal**, new to the spec (this note does not edit findings.md):

```yaml
record_key:
  columns: [name_hash]            # the designed column; record_id for a surrogate (as choose_record_key emits)
  found: false
  design: name_hash               # new value; or surrogate
  basis: [<name column>]          # new: the column the key is derived from
  rule: >-
    sha256 hex of part || 0x1F || name_norm@1(<name column>);
    name_norm@1 = NFKC, Unicode full case fold, NFKC, whitespace runs to one space, trim
    (pinned unidata_version, e.g. 15.0.0; a loader on another version stops); normalized once in Python and stored as <name column>_norm.
    A rename makes a new key.
    # for surrogate: "durable id given at first appearance and kept in a key map
    #   looked up by the sha256 above; renames and variants are aliases set by the operator"
  evidence:
    unique: true                  # existing
    null_rows: 0                  # existing
    persistence: null             # existing; null until compare sees a second delivery
    unique_raw: true              # new
    unique_after_normalization: true   # new
    folded_collisions: {groups: 0, examples: []}   # new; masked examples
    near_duplicates: {groups: 0, folds: [punctuation, accents, legal_form], examples: []}  # new, probe only
    provisional: true             # new; true until persistence is measured
```

The question to the operator goes in findings.md §8 `questions`. The record key cannot be approved until it is answered or the default is accepted.

### 4.4 Names in MDM are match attributes, not identity

MDM tools treat names as inputs to fuzzy matching.

- Reltio configures organization names with an `OrganizationNamesComparator` or `DamerauLevenshteinDistance` comparator, an `OrganizationNameMatchToken` and the `Fuzzy` operator. It configures person names with exact, edit-distance or phonetic (`DoubleMetaphone`) comparators [N10].
- That page does not say whether a name alone may merge two records [N10].
- The conclusion that names are match attributes and not identity is this note's inference from that configuration. It agrees with note 01's operator ruling that a name-match rule needs at least 600 labelled pairs, with a 95% lower bound on precision of at least 99.5%.

So for a part that MDM masters:

- the name key is the source's *record key* only. It is local, and like note 01's surrogate it is never sent to the cross-reference table;
- the name, normalized and raw, goes to MDM as a **match attribute**;
- the record key never decides that two sources' records are the same thing.

### 4.5 The one question for the operator

> "When a record's name changes, is it still the same record, or a new one?"

- **"A new one"** (the name *is* the thing): use `name_hash`.
- **"The same one"**: use `surrogate` with a key map and aliases.
- **No answer**: use `surrogate`, with `provisional: true` until `compare` measures persistence.

### 4.6 What the profiler would change (for the implementing ticket, not done here)

- `keys.py`: add `name_basis(con, part, columns)`, run after `unique_keys` returns nothing. `choose_record_key` then fills in `basis`, the new evidence fields and the `rule` above.
- Normalization lives in one Python function, `name_norm@1`, which the profiler and every loader import. No SQL engine re-implements it.
- `compare`: add renamed-suspect and reused-suspect counts for parts whose key is name-based.

## Examples

These illustrate the generic rules. No data was fetched for them.

- **A Company list carrying only the legal name.**
  - Companies rename after mergers, so the answer to §4.5 is "the same one". Use `surrogate`.
  - Normalizing `Acme, Inc.` and `ACME INC.` with `name_norm@1` keeps the comma and the dot, so they stay two distinct strings. Stripping punctuation and legal-form words would merge them, but it would also merge unrelated `Acme` firms. Leave that to MDM matching, where an issued identifier (a registry number, an LEI from GLEIF) can confirm a match.
- **A product catalogue where a new name means a new product.**
  - The answer to §4.5 is "a new one", so `name_hash` fits. Two deliveries must still show no renamed suspects.
- **A Person list with names only.**
  - Names are personal data, and homonyms are common. Never use the name as a key: §3 test 4 rules it out. Use `surrogate`, and match persons only through MDM's name-match rules.
- **A reference code list whose only column is a long description** (for example, a list of filing form descriptions with no codes).
  - Labels change rarely, and a changed label usually means a new meaning. `name_hash` fits once `folded_collisions` = 0.

## Sources

Primary sources were read on 2026-10-05 (ET). Pages not read online are marked.

- N1 RFC 9562, *Universally Unique IDentifiers (UUIDs)*, §5.5 (UUIDv5), §6.5 (name-based generation), §8: https://www.rfc-editor.org/rfc/rfc9562.html
- N2 Unicode Standard Annex #15, *Unicode Normalization Forms*, revision 58, §1.1 (Figure 2), §1.2 (Table 1), §3 (stability): https://unicode.org/reports/tr15/
- N3 The Unicode Standard, Version 18.0, ch. 3 §3.13, R4 `toCasefold`, D144–D147 (caseless, canonical, compatibility and identifier caseless match): https://www.unicode.org/versions/Unicode18.0.0/core-spec/chapter-3/
- N4 NIST FIPS 180-4, *Secure Hash Standard*, Aug 2015: §6.2 (SHA-256), §7 (truncation), the "called secure because" clause, and App. A.1 (refers to SP 800-107, which this note did not read): https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.180-4.pdf
- N5 Kimball Group, *Natural, Durable, and Supernatural Keys*: https://www.kimballgroup.com/data-warehouse-business-intelligence-resources/kimball-techniques/dimensional-modeling-techniques/natural-durable-supernatural-key/
- N6 Kimball Group, *Dimension Surrogate Keys*: https://www.kimballgroup.com/data-warehouse-business-intelligence-resources/kimball-techniques/dimensional-modeling-techniques/dimension-surrogate-key/
- N7 Data Vault 2.0 hash keys.
  - The only primary text read is the DataVaultAlliance FAQ line "business keys – known as durable keys in the Kimball Model": https://datavaultalliance.com/news/faq-about-data-vault-2-0/
  - The TRIM(UPPER(business key)) hashing formula and the parallel-load reason come from a secondary course page **(excerpt)**: https://apxml.com/courses/building-scalable-data-warehouses/chapter-2-advanced-data-modeling-scale/data-vault-implementation
  - The canonical source, not read online: D. Linstedt and M. Olschimke, *Building a Scalable Data Warehouse with Data Vault 2.0*, Morgan Kaufmann, 2015.
- N8 PostgreSQL 18 documentation:
  - §9.4 string functions (`md5`, `normalize`, `casefold`, `lower`): https://www.postgresql.org/docs/current/functions-string.html
  - §9.5 binary string functions (`sha256`, `md5`): https://www.postgresql.org/docs/current/functions-binarystring.html
  - §9.14 UUID functions (`gen_random_uuid`, `uuidv4`, `uuidv7`): https://www.postgresql.org/docs/current/functions-uuid.html
  - `uuid-ossp` (`uuid_generate_v5`): https://www.postgresql.org/docs/current/uuid-ossp.html
  - That `casefold` is absent from versions 16 and 17 was checked against https://www.postgresql.org/docs/16/functions-string.html and …/docs/17/…
- N9 DuckDB documentation source (`docs/current/sql/functions/utility.md` and `text.md`: `hash`, `md5`, `md5_number`, `sha1`, `sha256`, `uuid`, `gen_random_uuid`, `uuidv7`, `nfc_normalize`, `strip_accents`, `lower`): https://github.com/duckdb/duckdb-web/tree/main/docs/current/sql/functions
- N10 Reltio, *Match Strategies for the Most Common Attributes* (summary of the page): https://docs.reltio.com/en/reltio/what-reltio-does-at-a-glance/data-unification-and-mdm-at-a-glance/data-unification-and-mdm-in-detail/reltio-match-and-merge/match-strategies-for-the-most-common-attributes
- The collision probabilities in §2.3 were computed in this note from the birthday bound.

Repository: `skills/data-profiling/scripts/profiling/keys.py` (`_candidates`, `choose_record_key`); `docs/specs/profiling/findings.md` section 3 (`record_key`); `.scratch/profiling/research/01-classify-and-profile.md` section 4.
