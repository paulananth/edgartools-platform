# Trial log — onboarding `sec.company_profile`

## Questions

| # | Question | SPEC section looked in | What I assumed | Resolved by |
|---|---|---|---|---|
| 1 | How do I read a file that is ONE pretty-printed JSON object (not JSONL)? §8.1 only lists `records: jsonl` and `record_path`. | §8.1, §22 | `format: json` with no `records:` = one document per file; `each: "."` = one row. | Trying it (case passed). No error message involved. |
| 2 | JSON scalars have no `$` key. Does `text: { path: cik }` work, or must it end in `.$`? §8.2 says "text is under `$`", which is true for GLEIF's JSON but not SEC's. | §8.2, §8.3 | Plain key path works. | Trying it (worked silently). |
| 3 | In `join` over a list of **scalars** (`tickers: ["DHC","DHCNI"]`), what path reads the item? GLEIF uses `path: $`. | §8.3, §9 (`join`), §22 | First copied GLEIF's `$`: it silently read `""` for every item (`",,"`). Switched to `path: "."` ("the current item", §8.3), which worked. | A **case diff**, not a runner error. `$` on a scalar should be an error or be specified. |
| 4 | What happens to a row whose `kind_field` value is not in `kind_values` ("no fallback")? Fail the batch, drop, or defer? | §13.1, §13.2, §16 | Probed with an `expect.mdm` row. | Case diff showed kind `unsupported_identity_kind` with no identifiers. The gate reports **no** metric for these (no `deferred` line appears), so 356 of 400 rows silently map to nothing. Follow-up probe: adding `retain_deferred: true` changed nothing (same kind, same metrics), and a declared gate limit `deferred: { max: 0 }` was **silently ignored** (no metric line, no error). Reverted both; the final contract has neither. |
| 5 | §13.4 **rejects** `kind_values` over an SEC `entityType` for Form 3/4/5, but the task asks for exactly that here. | §13.4 | Followed the task. Real-data finding: `entityType: other` covers persons AND listed foreign private issuers (Wisekey, Brookfield Wealth Solutions, Oddity Tech, Click Holdings, Mitsui), so real companies do not become Companies. Pinned by a Named Case. | Not resolved; data inspection. |
| 6 | Identifier namespace for the CIK: §13.1 says "only `sec_cik` exists as a format". Is `sec_cik` also the namespace? Is `identifier_formats` needed? Does the formatter take the zero-padded string? | §13.1 | `identifiers: { sec_cik: cik }`, no `identifier_formats`, `cik` kept as the 10-digit string. | Cases passed with `sec_cik: "0001001385"`; I cannot tell whether a formatter ran. |
| 7 | The Mastering Policy (`policies/mastering-policy.yaml`) lists `name` sources as `[sec.ownership, gleif.level1]`. How does a new source contribute Company fields without editing a file outside its folder (acceptance check 1)? | §4.4, §5, §13.1, §21 | Left the policy alone; mapped fields anyway. | Unresolved. Also: MAPPING.md shows `sic`, `tickers` etc. as "field …" although §13.1 says a field not in the policy is evidence only; mapdoc does not flag that. |
| 8 | Values for the free-text Dataset Contract parts (`provider`, `family`, `record_key`, `publication_key`, `effective_time`, `semantics`). §13.3 says `family` changes behaviour and points to research 01 §3, which is not available. | §13.3 | Invented plausible values (`family: submissions`, etc.); omitted `registry_evidence`. | Unresolved; no error either way. |
| 9 | Do `pattern` / `in_set` treat `null` as a violation? | §14 | Assumed nulls are skipped. | Gate: `pattern(sic)` = 0 violations with 352 null `sic` → nulls skipped. |
| 10 | Can a case fixture hold several documents (a folder, a list)? With one-JSON-per-file, every case has exactly one row, so a merge case with `bound` + `binding_required` for two records cannot be written in one case. | §15 | One file per case; merge case covers `bound` only. | Unresolved. |
| 11 | Call shape of an argument-less chain step (`empty_to_null`). | §8.5, §9 | `{ empty_to_null: {} }`. | Worked. |
| 12 | Custom check wiring: inputs are silver column names? Module name `source_contract` vs prototype `source_engine`? | §11, §14 | `from source_contract import check_step`; inputs `[ticker_count, exchange_count]`. | Worked. No `requires` needed (stdlib only). |
| 13 | §17/§25.2 say the prototype prints state `draft` (exit 0) when cases pass but the gate was not run. My first stub, run without `--gate`, printed **`version proven`**, exit 0. | §17, §25 item 2 | Always ran with `--gate` for the final proof. | Contradiction between spec and runner; unresolved. |
| 14 | `silver.collapse` — required? | §12, §25 item 6 | Omitted (grammar is Open); schema does not require it. | Worked. |
| 15 | Type for fiscal year end (`MMDD`, e.g. `0930`) and where former-name `from`/`to` dates go when silver must be one row per subject (§13.2). | §12, §13.2 | `fiscal_year_end: string?`; former names joined by `\n` plus a `former_name_count bigint`; dates dropped (a second table would not feed MDM). | Judgement call. |
| 16 | Gate `rows.<table>` floor for `select: all` over a growing family. | §16 | `min: 400` (the current batch). | Judgement call. |
| 17 | Is `field_shape` a bare scalar (`nullable_text`) or a per-field map? §13.1 says any other value is silently ignored, so the runner cannot tell me whether mine took effect. | §13.1, §13.2 | Bare scalar `field_shape: nullable_text`. | Unresolved; no example uses it. |

## Errors met

Every non-zero exit from `./source` (no exit 2 or 3 was ever hit; the `retain_deferred` / `deferred` probes exited 0):

1. **exit 1** — stub case: `tickers expected DHC,DHCNI,DHCNL actual ,,`. Cause: `join` parts used GLEIF's `path: $` on scalar list items. Changed to `path: "."`.
2. **exit 1** — `stub other expected 0 assertions, got 1`. I expected an `other` row to produce no MDM assertion. Replaced `mdm: []` with a guessed row to get a diff.
3. **exit 1** (deliberate probe, `--json`) — diff `kind expected company actual unsupported_identity_kind`, `identifiers.sec_cik actual null`. Changed the non-operating cases to expect `{ kind: unsupported_identity_kind }`.
4. **exit 1** (deliberate sanity check, reverted) — narrowed `in_set(entity_type)` to `[operating]` and `pattern(sic)` to 3 digits to confirm checks really fire inside Named Cases; got 6 located violations with row keys. Restored the contract.

## Files read

In order:
1. `SPEC.md`
2. `families.local.yaml`
3. `source` (the runner wrapper script)
4. `sources/gleif/contract.yaml`
5. `sources/gleif/MAPPING.md`
6. `engine/contract.schema.json`
7. `engine/source_contract.py`
8. `policies/mastering-policy.yaml`
9. `data/sec-company-batch/1001385.json` (first 80 lines, pretty-printed)
10. `data/sec-company-batch/*.json` — all 400, through a local profiling script (shape of each field, entityType values, list lengths, empty-string vs null)
11. `data/sec-company-batch/1034380.json` (full, without `filings`)
12. `sources/sec-company/fixtures/*.json` (field extracts, to write expectations)

Directory listings of the sandbox, `sources/gleif/`, `engine/`, `policies/`, `data/sec-company-batch/`. Nothing under `engine/` other than the two permitted files was opened.

## Result

- **State: `version proven`** — `./source prove sources/sec-company --gate` exit 0.
- `sources/sec-company/contract.yaml`: **123 lines**; `custom.py`: 10 lines (one custom check, no custom columns: custom fraction 0 of 15).
- **6 Named Cases**: baseline operating company; three parallel tickers/exchanges (list trap); person filer with `null` fiscal year end, `""` SIC/state, empty lists (missing-field trap); listed foreign private issuer typed `other` (kind trap); operating company with `""` state of incorporation and two ordered former names; a merge case (`bound` via declared Steward binding, Docker, ~7 s).
- **Gate** over all 400 artifacts (batch `8563de3b94df`, 0.2 s): rows 400 (min 400), rejected 0, type_errors 0, and 9 checks all at 0 violations (`not_null(cik)`, `unique(cik)`, `pattern(cik)`, `not_null(name)`, `in_set(entity_type)`, `pattern(sic)`, `pattern(fiscal_year_end)`, `pattern(state_of_incorporation)`, `custom_check(tickers_pair_with_exchanges@1)`). No limit needed a `why:`.
- `sources/sec-company/MAPPING.md` generated by `./source mapdoc`.

Harder than it should be:
- An unknown/unimplemented gate limit key (`deferred`) is accepted and silently ignored, so a reviewer reading the gate would believe a limit is enforced.
- `path: $` on a scalar list item silently yields `""`. I only noticed because a case pinned the value. Nothing in the gate would have caught it.
- Rows whose kind is not in `kind_values` become `unsupported_identity_kind` assertions (89% of this batch) and no gate metric counts them. A contract could map almost nothing into MDM and still be `proven`.
- The source cannot win any Company field without a Mastering Policy edit outside its folder, and MAPPING.md labels policy-unknown fields as "field" instead of "evidence only".
- Without `--gate` the runner still says `version proven`, which contradicts §17.
