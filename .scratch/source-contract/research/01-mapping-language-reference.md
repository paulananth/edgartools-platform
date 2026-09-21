# Research: the Mapping Language (Clean MDM `adapter` block) reference

Ticket: `.scratch/source-contract/issues/01-write-the-mapping-language-reference.md`
Map: `.scratch/source-contract/map.md`
Date: 2026-09-21
Method: primary sources only: `edgar_warehouse/mdm/clean/*.py`, the Clean MDM
migrations it runs (`edgar_warehouse/mdm/migrations/023,027,029_*.sql`), tests
under `tests/` that exercise `mdm/clean`, the fixture contracts under
`tests/fixtures/clean_mdm/`, and `docs/specs/clean-mdm/*.md`. No code was run.
No network requests. Every claim about current behaviour cites `path:line`.
Text marked **PROPOSED** is a proposal. It is not a claim about the code.

Path abbreviations: `A` = `edgar_warehouse/mdm/clean/adapters.py`,
`E` = `.../clean/evidence.py`, `C` = `.../clean/cli.py`,
`S` = `.../clean/store.py`, `CS` = `.../clean/company_source.py`,
`SV` = `.../clean/survivorship.py`, `R` = `.../clean/relationships.py`,
`M` = `.../clean/merge.py`, `SP` = `.../clean/source_publications.py`,
`m023`/`m027`/`m029` = `edgar_warehouse/mdm/migrations/0NN_clean_mdm*.sql`,
`FX1` = `tests/fixtures/clean_mdm/v1/dataset.json`,
`FXP` = `tests/fixtures/clean_mdm/publication_v1/dataset.json`,
`TCS` = `tests/mdm/test_clean_company_source.py`,
`TPG` = `tests/integration/test_clean_mdm_postgres.py`.

## Summary

1. The `adapter` block has 15 top-level keys, plus 7 per-profile keys and 7 per-relationship keys. `normalize` reads them all (`A:49-158`). No schema validates them: `register_dataset` stores any body (`S:180-233`), and the SQL CHECK only requires 8 other keys (`m023:18`).
2. The adapter can raise 6 `UnsupportedRecord` reasons: `invalid_record_shape`, `invalid_identity_kind`, `unsupported_identity_kind`, `missing_record_identity`, `invalid_cik` and `invalid_field_shape` (`A:60`, `A:65`, `A:68`, `A:45`, `A:28`, `A:84`). Tests exercise only `unsupported_identity_kind`, `missing_record_identity` and `invalid_field_shape` (`TPG:1694-1699`, `TCS:88`). No file in `tests/` mentions `invalid_record_shape`, `invalid_identity_kind` or `invalid_cik`. The CLI adds `invalid_json_record` (`C:126`). Contract mistakes (a typo in a format name, a bad `kind_values` target, a missing required sub-key) are plain `ValueError`/`KeyError` exceptions. They stop the whole batch. They do not defer the record.
3. Many rules are in the code but no document states them. Examples: silent `None` for a path through a list, one row gives one assertion, `kind_field` overrides `kind`, relationships whose target is missing are dropped silently, relationship `target_key` values are never formatted, unknown `field_shape` values do nothing, and a JSON-object field value with `"op"` becomes an assertion operation.
4. `adapter.version` goes into `provenance`, and `provenance` goes into `assertion_id` (`E:88-90`). The store is unique on `(source_code, record_key, publication_key)` (`m023:50`). So a new adapter version cannot re-assert a publication that was already committed. The dataset body is also immutable per `source_code` (`S:217-224`). A mapping change therefore needs a new `source_code`.
5. Of the other Dataset Contract parts, only `family`, `schema_version`, `publication_families`, `publication_contract` and `registry_evidence` affect runtime behaviour. `provider`, `record_key`, `publication_key`, `effective_time` and `semantics` must be present but are free prose. `completeness` is prose and not even required.
6. GLEIF needs: joins across members (the relationship member is separate), mapping of relationship-type values, an `lei` identifier format, and time-zone-aware date handling. Form 3/4/5 needs: row explosion from nested XML (or pre-flattened silver), a multi-part ordinal key, a formatted cross-source target key (issuer CIK), and relationship-type mapping from role flags. It also needs a Person kind path. The proposals for Codex are in the last section.

## 1. Key reference: the `adapter` block

"Rejection" means what happens to one record. `UnsupportedRecord(reason)` is retained as a deferred record only when `retain_deferred` is true (`C:140-157`). Otherwise it is re-raised and the batch fails (`C:141-142`). "Crash" means a non-`UnsupportedRecord` exception. It fails the batch even with `retain_deferred` (`C:140` catches only `UnsupportedRecord`).

### 1.1 Top-level keys

| Key | Type | Req. | Meaning | Rejection / failure | Example (source) |
| --- | --- | --- | --- | --- | --- |
| `version` | string | **required** | Adapter version. Copied into `provenance.adapter_version` (`A:133`, `A:140`) and into the deferred provenance (`C:154`). | Missing gives a `KeyError` crash (`A:133`). | `"sec-company-landing-v1"` (`CS:42`), `"fixture-v1"` (`FX1:98`) |
| `kind` | string, one of `KINDS` | one of `kind`/`kind_field` | Fixed identity kind for every row (`A:61`). | Empty or absent with no `kind_field` gives `unsupported_identity_kind` (`A:67-68`). A value outside `KINDS` (`E:10-19`) crashes with `ValueError` in `assertion` (`E:53-61`). | `"company"` (`FXP:26`) |
| `kind_field` | dotted path | one of `kind`/`kind_field` | Row path whose value is looked up in `kind_values` (`A:62-66`). Overrides `kind` when present (`A:66`). | A non-string value gives `invalid_identity_kind` (`A:64-65`). A value with no entry gives `unsupported_identity_kind` (`A:66-68`). | `"entity_type"` (`CS:48`), `"kind"` (`FX1:6`) |
| `kind_values` | object string→kind | required if `kind_field` | Exact-match map from source value to kind (`A:66`). | Absent while `kind_field` is present gives a `KeyError` crash. An out-of-set target crashes (`E:54`). | `{"operating": "company"}` (`CS:49`) |
| `record_key` | list of dotted paths | **required** | Source-record identity (`A:69`, `A:42-46`). | Empty list, or any part `None`/`""`, gives `missing_record_identity` (`A:44-45`). Absent gives a `KeyError` crash. | `["cik"]` (`CS:46`), `["key"]` (`FX1:37-39`) |
| `record_key_format` | format name | optional | Applied to the finished key (`A:70`). `None` means `str().strip()` (`A:18-19`). | `sec_cik` failure gives `invalid_cik` (`A:20-28`). Any other name crashes with `ValueError("Unconfigured identifier format")` (`A:30`). | `"sec_cik"` (`CS:47`) |
| `identifiers` | object namespace→path | optional | Identifier values by namespace (`A:71-77`). | Values that are `None` or blank are skipped silently (`A:74`). Format errors as for `identifier_formats`. | `{"cik": "cik"}` (`CS:50`), `{"lei": "key"}` (`FXP:28`) |
| `identifier_formats` | object namespace→format | optional | Per-namespace format (`A:75-77`). | `invalid_cik`, or the unconfigured-format crash (`A:28`, `A:30`). | `{"cik": "sec_cik"}` (`CS:51`) |
| `fields` | object name→path | optional | Ordinary fields (`A:78-80`). The name must match a policy field for selection (`SV:200-203`). Otherwise the field is evidence only (`docs/specs/clean-mdm/merge-stage.md:158`). | Empty name crashes (`E:64-65`). A value that is an object with `"op"` is passed through as an operation. An invalid op crashes (`E:66-69`). | `FIELDS` (`CS:24-31`, `CS:52`) |
| `field_shape` | string | optional | Only `"nullable_text"` has an effect: every field value must be `None` or `str` (`A:81-84`). | `invalid_field_shape` (`A:84`, tested `TPG:1647-1648`, `TPG:1698`). | `"nullable_text"` (`CS:45`) |
| `profiles` | list of profile specs | optional | Role profiles (see 1.2) (`A:85-107`). | See 1.2. | `FX1:17-36` |
| `relationships` | list of relationship specs | optional | Reported edges (see 1.3) (`A:108-128`). | See 1.3. | `FX1:40-97` |
| `source_record_provenance` | bool | optional (default false) | When true, provenance becomes only `{record_key, adapter_version}`. Artifact hash, member and line locator are removed (`A:137-140`). | none | `true` (`CS:44`, `FXP:30`) |
| `provenance` | object name→path | optional | Source values copied into `provenance.source` (`A:141-144`). | none (missing paths give `None`) | `CS:53-59` |
| `retain_deferred` | bool | optional (default false) | Read by the CLI, not by `normalize`. Unsupported records become deferred evidence (`C:98`, `C:140-157`). Needs an exact `record_count` (`C:99-100`), and a line locator is added (`C:113-114`). | none | `true` (`CS:43`) |

### 1.2 Profile spec keys (`A:86-107`)

| Key | Type | Req. | Meaning / behaviour | Example |
| --- | --- | --- | --- | --- |
| `role` | **literal** string | required (`KeyError` otherwise) | Profile role. Survivorship accepts only `PROFILE_KINDS` roles (`adviser`, `audit_firm`, `fund`) that are compatible with the kind (`E:20-24`). Others open review `incompatible_profile` (`SV:139-148`). | `"adviser"` (`FX1:21`) |
| `authority` | **literal** string | required | Registration authority. Empty opens review `unproven_profile` (`SV:149-157`). | `"synthetic-test"` (`FX1:19`) |
| `registration` | dotted path | required | A `None` value skips the profile silently (`A:87-89`). Other values are passed through `str()` (`A:94`). | `"adviser_registration"` (`FX1:20`) |
| `jurisdiction` | dotted path | optional | `None` when the spec omits it (`A:95-97`). | none in any fixture or live contract |
| `valid_from` | dotted path | required (`KeyError` otherwise, `A:98`) | A missing value opens review `undated_profile` (`SV:158-166`). The value must parse with `instant` and include a time zone (`E:27-31`), or merge crashes (`SV:167`). | `"valid_from"` (`FX1:22`) |
| `valid_to` | dotted path | optional | Interval check `invalid_profile_interval` (`SV:167-177`). | none in any fixture or live contract |
| `fields` | object name→path | optional | Role-specific fields. `nullable_text` does **not** check them (`A:81-84` covers only top-level fields; profile fields are read at `A:102-105`). | none in any fixture or live contract |

### 1.3 Relationship spec keys (`A:109-128`)

| Key | Type | Req. | Meaning / behaviour | Example |
| --- | --- | --- | --- | --- |
| `type` | **literal** string | required | Must be a key of `R.CONTRACTS` (`R:12-48`). Otherwise review `unsupported_relationship` at projection (`R:91-93`). | `"MANAGES_FUND"` (`FX1:46`) |
| `target_key` | list of dotted paths | required | Target record key, built with the same `record_key()` rule (`A:111`). Missing or empty drops the edge **silently** (`A:110-113`). | `["managed_fund"]` (`FX1:42-44`) |
| `target_source` | **literal** `source_code` | required | Target subject = `digest([target_source, target_key])` (`A:117`, `E:34-35`). Nothing checks that this source is registered. | `"fixture.representative"` (`FX1:45`) |
| `scope` | **literal** string | optional (default `""`) | Groups edges for hierarchy checks (`R:150-151`). It is not a path. | none in any fixture or live contract |
| `valid_from` | dotted path | required (`KeyError` otherwise, `A:119`) | Missing value gives review `unknown_relationship_start` (`R:110-112`). The value needs a time zone (`R:60-63`, `E:27-31`). | `"valid_from"` (`FX1:47`) |
| `valid_to` | dotted path | optional | Interval check `invalid_relationship_interval` (`R:119-121`). | none in any fixture or live contract |
| `properties` | object name→path | optional | Edge properties (`A:123-126`). They are part of the edge identity digest (`R:136-137`). | none in any fixture or live contract |

Endpoint rules applied later, not by the adapter: both ends bound (`R:94-96`), not self (`R:99-101`), endpoint kinds allowed by `CONTRACTS` (`R:104-106`), both accepted (`R:107-109`), and required endpoint profiles cover the edge interval (`R:122-135`).

### 1.4 What `normalize` takes from outside the contract

- `publication_key`, `revision`, `effective_at` come from the manifest batch `input.publication` (`C:108-112`, `A:147-150`). They never come from the row. `effective_at` needs a time zone or `None` (`E:79-81`). The Company bundle sets it to `None` (`CS:208`).
- `artifact_sha256` and `member` come from the batch input (`C:109-111`). They are read even when `source_record_provenance` later removes them (`A:130-131`), so a caller without them gets a `KeyError`.
- `schema_version` is the dataset's top-level `schema_version` (`A:156`). It is not an adapter key.

## 2. Unstated rules (code behaviour no document states)

1. **Dotted paths, no arrays: one row gives one assertion.** `value()` splits on `.` and returns `None` as soon as the current value is not an object (`A:33-39`). A path through a list, or a list index like `owners.0`, yields `None` without an error. The CLI calls `normalize` once per non-blank JSONL line (`C:101-139`). Nothing can fan a row out into several subjects. A path segment cannot contain a literal `.`.
2. **Kind is an exact, case-sensitive lookup.** `kind_values.get(source_kind)` has no trimming, case folding or default (`A:66`). If both `kind` and `kind_field` are set, `kind_field` wins. On a miss the static `kind` is **not** used as a fallback: the record is `unsupported_identity_kind` (`A:61-68`). `normalize`'s docstring says "No name-based kind inference" (`A:54`). Tested: `TCS:88-94`, `TPG:1637-1641`.
3. **Relationships are dropped silently when the target key is missing.** `except ValueError: continue` (`A:110-113`). `UnsupportedRecord` subclasses `ValueError` (`A:9`), so this handler catches the base class. Any `ValueError` from `record_key()` is swallowed. Nothing records the drop: no deferred record, no review, no count. No file in `tests/` matches `target_key` outside the fixture declarations (`FX1:42-94`), so no test was found that exercises the drop.
4. **Relationship target keys are not formatted.** `record_key_format` and `identifier_formats` apply to the subject key and identifiers (`A:70`, `A:75-77`). They never apply to `target_key` (`A:111`, `A:117`). A target CIK of `320193` hashes to a different subject than a Company whose record key was padded to `0000320193`.
5. **Single-part and multi-part keys are encoded differently.** One path gives `str(value)`. Two or more give `canonical(list)`, a JSON array string (`A:46`, `S:23-30`). `record_key_format` is applied to that whole string (`A:70`), so `sec_cik` on a multi-part key always fails `invalid_cik`. Whitespace-only parts pass the `""` check (`A:44`), but `format_value("  ", None)` (no format name configured) strips them to `""` (`A:18-19`). `assertion()` then raises a plain `ValueError` (`E:55-61`), which crashes the batch instead of deferring the record. No test was found for multi-part keys or whitespace-only keys (searched `tests/` for `record_key`).
6. **There is a single `field_shape`.** Only `"nullable_text"` is checked (`A:81`). Any other value, including a typo, has no effect. Without it, lists and numbers pass through as `{"op":"value","value":...}` (`E:66-67`).
7. **A field value that is an object with `"op"` is an operation.** `E:66` passes `{"op": ...}` through unchanged. With no `field_shape`, a source value such as `{"op":"clear"}` becomes a clear, and `{"op":"bogus"}` crashes with `ValueError("Unknown assertion operation")` (`E:68-69`). The Company contract avoids this only because `nullable_text` rejects the value first (`TPG:1648`, `TPG:1698`). A mapped `None` becomes `{"op":"unknown"}` (`E:67`). An adapter cannot produce `clear`/`retract` from plain source values.
8. **There is a single identifier format.** Only `sec_cik` exists: ASCII digits, ≤10, non-zero, zero-padded to 10 (`A:20-29`). Any other name raises a plain `ValueError` (`A:30`), which crashes the batch. It is not an `UnsupportedRecord`. Identifiers without a format are `str(item).strip()` (`A:18-19`). Every namespace is treated as authoritative: two values in one namespace under one entity is `authoritative_identifier_conflict` (`M:397-407`).
9. **What `adapter.version` pins, and when it must change.**
   - It is written into every assertion's `provenance.adapter_version` (`A:133`, `A:140`) and every deferred record (`C:154`). Provenance is part of the hashed body (`E:88-90`), so the version is part of `assertion_id`.
   - Consequence: a new version applied to an already-committed `(source_code, record_key, publication_key)` gives a different `assertion_id` for the same unique tuple (`m023:50`). The insert uses `ON CONFLICT(assertion_id) DO NOTHING` (`m023:166-168`), so the other unique constraint raises. The same assertion id with a different body raises `Assertion identity collision` (`m023:163-165`).
   - The dataset body (adapter included) is immutable per `source_code`: "Dataset contract is immutable; register a new versioned contract" (`S:217-224`).
   - Therefore **any** change to the adapter block, not only `version`, needs a new `source_code` (the live code carries `.v1`, `CS:23`).
   - A new `source_code` also means a new subject for every record: `subject = digest([source_code, record_key])` (`E:34-35`, `E:83`). Old assertions keep the old subjects. Their identity bindings do not carry over, so the new subjects need new bind decisions or a merge before they reunite with the same entity. This is why the map's "Change and replay" open item is hard. A changed `version` inside the same `source_code` is impossible. No document states when to bump; `docs/specs/clean-mdm/state-of-build.md:162-165` only says the bundle suffix `company-v2` is not a schema version.
10. **Transport independence depends on `source_record_provenance`.** Without it, `artifact_sha256`, `member` and (with `retain_deferred`) the line locator `sha256:line:N` (`C:113-114`) enter the provenance, and so the assertion id. The same fact in a re-ordered or re-bundled file becomes a new assertion. With it, identical facts collapse (tested `TCS:113-133`, `TPG:1816-1845`). The spec requires this behaviour ("Exclude … transport paths … from business hashes", `docs/specs/clean-mdm/source-evidence.md:30-34`), but the key defaults to false and `FX1` omits it.
11. **Collections are snapshots; fields are patches, whatever `semantics` says.** Survivorship replaces identifiers, profiles and relationships with the latest assertion's lists (`SV:60-63`, `SV:101`). It keeps earlier field values across `unknown` (`SV:47-59`). The contract's `semantics` value is never read (item 3). This matches `docs/specs/clean-mdm/source-evidence.md:54-57`. An adapter must emit the **complete** identifier/profile/relationship set on every row.
12. **Batch limits apply to every source.** ≤16 MiB per member (`C:84-86`), ≤1000 records per member (`C:104-107`), exact `record_count` when retaining deferred records (`C:99-100`, `C:158-159`). Malformed JSON and non-finite numbers become `invalid_json_record` (`C:115-131`, `TPG:1646`, `TPG:1649`).
13. **Literal and path keys share one syntax.** `role`, `authority`, `type`, `target_source` and `scope` are literals. All other string values are paths. Nothing in the block marks the difference.

## 3. Dataset Contract parts

Three live bodies exist: `CS:32-61`, `FX1`, `FXP`, and inline in `TPG:133-146`. The only prose spec is one table row (`docs/specs/clean-mdm/source-evidence.md:23`).

**Code-read** means runtime behaviour depends on the value. **Presence-only** means the SQL CHECK requires the key (`m023:18`) but no code reads its value. **Prose** means neither.

| Part | Status | What the code does | Observed values | **PROPOSED** closed set / validator rule |
| --- | --- | --- | --- | --- |
| `provider` | presence-only (`m023:18`) | nothing | `"SEC"` (`CS:33`), `"synthetic-test"` (`FX1:102`), `"synthetic-offline-gleif-shape"` (`FXP:2`), `"test"` (`TPG:138`) | **PROPOSED**: enum `{SEC, IAPD, PCAOB, GLEIF}`, extended by a spec change. `source-evidence.md:16-19` separates provider from authority, and no `authority` key exists yet. |
| `family` | **code-read** | Must equal the registry coverage `source_family` (`S:196-210`, `m023:157`). Must equal the publication manifest's family (`SP:192-199`). Scopes family checkpoints (`m029:23-27`). | `"submissions"` (`CS:34`), `"fixture"` | **PROPOSED**: must be an existing `source_registry_coverage.source_family`. The validator checks it against the registry, not an enum. |
| `schema_version` | **code-read** | Copied into every assertion (`A:156`) and deferred record (`C:148`). The commit rejects a mismatch (`m023:160-162`, `m027:39-41`). `revision_versions.schema_version` is also compared (`SP:166-172`, `SP:231`). | `"silver-company-v1"` (`CS:35`), `"1"` | **PROPOSED**: equal to the Source Contract's declared silver table id plus version (e.g. `silver-<table>-v<N>`). A silver schema change needs a new `source_code` (rule 9). |
| `record_key` | presence-only | nothing; `adapter.record_key` is the real key | `"zero-padded 10-digit CIK"` (`CS:36`), `"key"` | **PROPOSED**: generate it from `adapter.record_key` + `record_key_format`. Do not hand-write it. |
| `publication_key` | presence-only | nothing; the real key is in the manifest (`C:108-112`), built in code for Company (`CS:178`) | prose sentence (`CS:37`), `"publication"`, `"version"` | **PROPOSED**: a template with a closed set of tokens, e.g. `{capture_run}`, `{member}`, `{member_sha256}`, `{native_publication}`. |
| `effective_time` | presence-only | nothing; `effective_at` comes from the manifest (`A:150`) | `"unknown; last_synced_at is observation time only"` (`CS:38`), `"publication effective time"`, `"effective_at"` | **PROPOSED**: enum `{unknown, publication, record_path:<path>}`. `record_path` is **not implemented**: `normalize` has no per-row effective time. `unknown` must pair with policy `allow_unknown_effective` (`CS:68`, `SV:216-219`). |
| `semantics` | presence-only | nothing (rule 11) | `"patch"` everywhere | **PROPOSED**: enum `{patch, snapshot}`. `snapshot` has **no implementation**. `merge-stage.md:125`, `:132-133` requires full-record datasets to state whether omission means unknown or retraction. |
| `completeness` | prose; **not** in the CHECK | nothing | one sentence (`CS:39`) | **PROPOSED**: enum `{bounded_sample, full_baseline, delta}`, aligned with the publication `mode`/`coverage` pairs (`SP:207-223`) and the Company bundle `scope.mode` (`CS:180`). |
| `adapter` | required by the CLI (`C:98`), not by the CHECK | section 1 | — | **PROPOSED**: required, with a JSON Schema for section 1. |
| `publication_families` | code-read when used | Checkpoint family membership (`m029:23-27`). The publication contract family must be a member (`SP:153-154`). | `["golden_copy"]` (`FXP:4`) | **PROPOSED**: nonempty list of registered family names. |
| `publication_contract` | code-read when used | `version` = 1, `format` = `clean-mdm-publication-v1`, `continuity` = `sequence-predecessor-sha256-v1`, `required_members`, `replacement_scope`, `revision_versions` (4 keys) (`SP:145-172`) | `FXP:10-23` | Already closed by `SP:148-172` and documented (`docs/specs/clean-mdm/source-publications.md:13-21`). |
| `registry_evidence` | **code-read**; added by `register_dataset` (`S:211`) | Must be active with matching version and family (`m023:155-158`) | — | Never authored. The validator must reject it in authored files. |
| authority, supported kinds/roles/fields, deletion semantics, enabled consumers | listed in `source-evidence.md:23`; **absent from code** | — | — | **PROPOSED**: kinds/roles derive from the `adapter` block. Consumers already live in the policy `required_consumers` (`CS:65`, `S:163-169`). |

## 4. Gaps for GLEIF and Form 3/4/5 (**PROPOSED**, for Codex via `.scratch/handover/`)

These are proposals. Nothing below is implemented. Each gap names the line that blocks it.

### GLEIF

- **G1 Relationships live in a separate member.** The fixture's relationship rows are `{child, parent, type}` in `relationships.jsonl`, separate from `level1.jsonl` (`tests/fixtures/clean_mdm/publication_v1/`). Golden Copy requires the members together (`docs/specs/clean-mdm/source-publications.md:24-26`). But a batch input is one member (`C:78-88`), and relationships attach to the current row's subject (`A:108-128`). **Proposal:** allow a relationship-only dataset whose record is the relationship row: `subject_key: [child]`, `target_key: [parent]`, and no kind/fields. This needs `normalize` to accept a record that asserts only an edge. `assertion()` currently requires a kind (`E:53-54`), and `SV:60-63` would overwrite the Level 1 subject's collections with the RR row's, so the RR subject must be distinct or collections must merge by source.
- **G2 Relationship-type value mapping.** GLEIF types (fixture `accounting_consolidation`) do not equal `R.CONTRACTS` keys (`ACCOUNTING_PARENT`, `R:25`), and `type` is a literal (`A:116`). **Proposal:** `type_field` + `type_values`, the same exact-lookup pattern as `kind_field`/`kind_values` (`A:62-66`).
- **G3 LEI identifier format.** Only `sec_cik` exists (`A:20-30`). **Proposal:** add `lei` (20 uppercase alphanumerics; ISO 17442 check digits), with failure reason `invalid_lei`. Make unknown format names fail at registration, not at the first row (`A:30`).
- **G4 Date values without a time zone.** GLEIF dates must become time-zone-aware `instant` strings (`E:27-31`) before `valid_from` can work (`R:60-63`, `SV:158-167`). The adapter has no value transforms. **Proposal:** a closed transform set on paths (`date_utc`, `upper`, `strip`), declared per path. Or require silver to store ISO UTC; the Source Contract `silver` block could then state that.
- **G5 Per-row effective time.** `effective_at` is one per publication (`A:150`). **Proposal:** optional `effective_at` path in the adapter, with the manifest value as fallback.
- **G6 REPEX members.** A reporting-exception row is evidence of "no parent reported", which the spec says is not proof of no parent (`docs/specs/clean-mdm/source-evidence.md:84`). The adapter has no disposition other than assertion or deferral. **Proposal:** route it through `retain_deferred` with a declared reason, or add a record type for it.

### Form 3/4/5

- **F1 Nested XML gives many rows.** One filing has many owners and transactions. The adapter is one line to one assertion (`C:101-139`, rule 1). **Proposal:** keep explosion in the Source Contract `read`/`silver` layer (the map's Q4 escape hatch), so the adapter reads `sec_ownership_reporting_owner` rows (key `accession_number, owner_index`, `edgar_warehouse/silver_schema.py:683-686`). No adapter change is needed. The contract must say so.
- **F2 Ordinal key.** `owner_index` is an ordinal inside a filing. `docs/specs/clean-mdm/source-evidence.md:36-39` allows ordinal keys only when the contract defines ordinal identity inside an immutable publication. **Proposal:** use the owner CIK as the Person/Company subject key (`owner_cik`, `silver_schema.py:427`). Keep `(accession, owner_index)` only as the provenance locator. Add a contract flag `ordinal_identity: true` when an ordinal key is chosen deliberately.
- **F3 Kind from role, not a single field.** Owners are persons or companies. The silver row has `owner_entity_type`/`owner_org` (`silver_schema.py:445`, `:450`), not a kind column. **Proposal:** `kind_values` over `owner_entity_type`, with unmapped values deferred as `unsupported_identity_kind` (exact lookup, rule 2). No inference from names (`A:54`).
- **F4 Formatted cross-source target.** `INSIDER_OF` must target the issuer's `sec.submissions.company.v1` subject, whose key is the padded CIK (`CS:46-47`). Target keys are never formatted (rule 4). **Proposal:** `target_key_format` on the relationship spec. **Unverified:** the reporting-owner row's column list has no issuer CIK (`silver_schema.py:424-451`), and `issuer_name` appears elsewhere (`:516`). So the target key needs a join to the filing row, or a silver column that must be added. This is not proven available.
- **F5 Relationship type from boolean flags.** `is_director`/`is_officer`/`is_ten_percent_owner`/`is_other` (`silver_schema.py:429-432`) all map to `INSIDER_OF` with a role property. **Proposal:** a conditional relationship `when: <path>` (emit only when truthy). Also: record dropped edges in accounting instead of dropping them silently (rule 3).
- **F6 Person kind and privacy.** `person` is a valid kind (`E:12`). Person projection, field set and privacy are open in `docs/specs/mdm/policy-language.md:494-505` (§15 item 4). **Proposal:** a Form 3/4/5 contract cannot go live until that item is closed. Mapping and parse tests can run before then.

### Cross-cutting proposals

- **X1 Validate at registration.** Add a JSON Schema for section 1, checked in `register_dataset` (`S:180-233` validates nothing today). This turns the crash cases in rules 5, 7 and 8 into registration errors that name the key. It serves acceptance check 9 in `map.md`.
- **X2 Mark literals.** Separate literal keys from path keys (rule 13), e.g. `{"path": ...}` vs `{"const": ...}`, or a documented fixed list.
- **X3 Default `source_record_provenance` to true** for new contracts (rule 10, `source-evidence.md:30-34`).
- **X4 Document the versioning rule**: any adapter change gives a new `source_code` (rule 9), and state how replay meets the Merge Stage's bounded rebuild. This is the map's "Change and replay" open item.
