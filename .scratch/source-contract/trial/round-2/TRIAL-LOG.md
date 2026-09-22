# Trial log: onboarding `sec.company_profile`

## Questions

1. **What does a deferred row look like in `expect.mdm`?**
   Where I looked: §13.4 (a kind value outside `kind_values` becomes a deferred record), §15 (the `expect.mdm` shape), §26 ("`deferred` ... not prototyped").
   What I assumed: that deferred rows give no assertion, so I first wrote `mdm: []`.
   Before that, case 4 had no `mdm:` key at all, and that version passed `--gate` and was proven. So leaving `mdm` out gives a passing case that proves nothing about the kind: the runner never makes an author face this.
   Resolved by a runner error: "expected 0 assertions, got 2". A second probe showed the diff `kind: expected company, actual unsupported_identity_kind` with `identifiers.cik: null`. So a deferred row is an assertion of kind `unsupported_identity_kind` with no identifiers. The spec never names that kind. I now expect `{ kind: unsupported_identity_kind }` for each `other` row.

2. **Should former names be a joined column or a child table?**
   Where I looked: §12 recommends a child table for "former names with their dates". The task says "one silver row per document with ... former names".
   What I assumed: both. The dataset table has a joined `former_names` column plus `former_name_count`, and an evidence table `sec_company_former_name` has one row per name. No error was involved.

3. **How does a child table carry its parent's key?**
   Where I looked: §8.4 ("`from: document` reads from the document root") and §9 (`from` is optional on `text`).
   What I assumed: `cik: { text: { path: cik, from: document, default: null } }` inside `each: formerNames`. It worked. The spec has no example of it, though. The Mapping Document also shows this column as `text` `cik` without saying `from: document`, so a reader cannot tell it comes from the parent.

4. **Is `completeness` allowed in `dataset.contract`?**
   Where I looked: §13.3 lists it, but the §22 GLEIF example leaves it out, and the §13.3 prose list of required and free-text parts does not mention it either.
   What I assumed: include it as `bounded_sample`. The runner accepted it without comment, so I can't tell whether it is read.

5. **Should I author `registry_evidence`?**
   Where I looked: §13.3 says "Never author `registry_evidence`", but the worked example (§22) and `sources/gleif/contract.yaml` both author it (`prototype`).
   What I assumed: follow the rule, not the example, so I left it out. The runner accepted that. No error was involved.

6. **Which MDM fields should I map, given the policy?**
   Where I looked: §13.2a and `policies/mastering-policy.yaml`. `company.name` ranks only `sec.ownership` and `gleif.level1`. `jurisdiction` and `country` rank only GLEIF.
   What I assumed: map `name` only. The source wins nothing, and the Mapping Document says so ("evidence only: the Mastering Policy gives `sec.company_profile` no rank"). I did not map `state_of_incorporation` to `jurisdiction`. SEC codes (`DE`, `V8`, `L3`) are not GLEIF's jurisdiction codes, and the spec gives no guidance on value vocabularies. No error was involved.

7. **What is `max_pct` of, for `deferred`?**
   Where I looked: §16 ("a percentage of the rows in the metric's table").
   What I assumed: the rows of `dataset.table`. The runner confirmed this: 356 was shown as 89.000%. In the end I used an absolute `max: 356`, because the batch is pinned. No error was involved.

8. **How are two checks of the same kind on the same column name, in different tables, told apart in the gate?**
   Where I looked: §14 (`check.<name>(<argument>)`, where the argument is only the column).
   What I assumed: nothing. I avoided the case: I did not add `not_null(cik)` on the child table, because it would collide with `check.not_null(cik)` on the main table. The gate naming has no table component, so this looks like a real spec gap.

9. **Does `each` on a list of plain strings plus `path: "."` work, and is `count` allowed without `default`?**
   Where I looked: §8.2 and §9.
   What I assumed: yes to both, as the spec says. It worked. No error was involved.

10. **What does the `timestamp` silver type accept?**
    Where I looked: §9 (`timestamp` "the text as written") and §12.
    What I assumed: that ISO `1996-11-12T05:00:00.000Z` passes, and it did (type_errors 0). The accepted format is not written down.

11. **How does `record` in `given.identities` handle a zero-padded CIK?**
    Where I looked: §15 ("the plain value for a one-part key").
    What I assumed: the raw silver value `"0001001385"`, quoted so it stays text. It worked. The spec does not say whether `identifier_formats` changes the record key. It seems not to: the key is the silver value.

12. **Is the merge case worth writing when the source wins no field?**
    Where I looked: §15 and §13.2a.
    What I assumed: yes, for `bound` and `binding_required` only, with no `winner` line, because this source cannot win `name`. Docker (Colima) was available, and the case passed in about 24 s.

13. **What should I do about `allow_unknown_effective` when I cannot touch the policy?**
    Where I looked: §13.3 says `effective_time: unknown` needs the policy to be given `allow_unknown_effective`.
    The problem: `policies/mastering-policy.yaml` is read-only and never names `sec.company_profile`, and §5 forbids naming the source outside its folder. So the spec asks for a paired change the author cannot make.
    What I assumed: write `effective_time: unknown` and leave the policy alone. It doesn't matter here, because the source wins no field. No error was involved.

## Errors met

The first draft contract proved on its first `--gate` run.

- #1 and #4 below were deliberate mutations, run to check that the cases really compare.
- #2 and #3 were real authoring errors, caused by the gap in Question 1.

| # | Command | Exit | Message | What I changed |
|---|---|---|---|---|
| 1 | `prove --json` after I deliberately broke `ticker_count` (3 to 2) and the mdm `name` | 1 | two `case` failures with diffs at contract lines 91 and 97 | reverted (this confirmed the cases really compare) |
| 2 | `prove --json` with `mdm: []` on the `other` case | 1 | `expected 0 assertions, got 2` at `/tests/3/expect/mdm` | probed further (Question 1) |
| 3 | `prove --json` expecting `kind: company` for `other` rows | 1 (hidden by a pipe) | diff `kind: company vs unsupported_identity_kind`, `identifiers.cik: 0001034380 vs null` | set `{ kind: unsupported_identity_kind }` for both rows |
| 4 | `prove --json` after I deliberately made the unbound record `bound` | 1 (hidden by a pipe) | `record 0001075415 expected bound, actual binding_required` | reverted (this confirmed the merge case really checks) |

## Files read

1. `SPEC.md`
2. `source`
3. `families.local.yaml`
4. `policies/mastering-policy.yaml`
5. `sources/gleif/contract.yaml`
6. `sources/gleif/MAPPING.md`
7. `sources/gleif/fixtures/three-records.jsonl` (first 600 bytes)
8. `sources/gleif/fixtures/batch/level1.jsonl` (line count only)
9. `engine/contract.schema.json`
10. `engine/source_contract.py`
11. `data/sec-company-batch/1001385.json` (the structure)
12. `data/sec-company-batch/*.json`: all 400, parsed by a script to profile field shapes, null and empty counts, and entity types
13. `data/sec-company-batch/1034380.json`, `1738699.json`, `1638097.json` (full profile fields)

## Result

- **State:** `version proven`. `./source prove sources/sec-company --gate` exits 0 with 5 cases and 0 failures, the merge case included.
- **Contract:** `sources/sec-company/contract.yaml` is 133 lines. It has two silver tables, `sec_company_profile` (14 columns, fed to MDM) and `sec_company_former_name` (5 columns, evidence), and 0 Custom Steps (custom fraction 0 of 19).
- **Cases (5):**
  1. The happy path, with silver, the former-name child row and the mdm assertion.
  2. A list of three tickers and exchanges.
  3. An operating company with no tickers: null joins, zero count.
  4. The trap case: the `other` person HALBERT DAVID D (with `""` sic and state, a null fiscal year end and an all-null address) and the `other` listed foreign company Wisekey. Both are read and both are deferred as `unsupported_identity_kind`.
  5. A merge case: a declared binding gives `bound`, and an unbound operating company gives `binding_required`.
- **Fixtures:** 1001385, 1075415, 1954360, 1034380 and 1738699, copied from `data/sec-company-batch/`.
- **Gate metrics** (400 artifacts, batch `8563de3b94df`):
  - rejected 0, type_errors 0;
  - deferred 356 (89%) against a limit of `max: 356`, with a `why`;
  - rows.sec_company_profile 400 (min 400), rows.sec_company_former_name 50 (min 50);
  - all 8 checks had 0 violations: not_null(cik), not_null(name), unique(cik), pattern(cik), in_set(entity_type), pattern(fiscal_year_end), unique(cik,name_index), not_null(former_name).
- **Mapping Document:** `sources/sec-company/MAPPING.md` is generated.
- **What felt harder than it should:**
  - How deferred rows render in `expect.mdm` (`unsupported_identity_kind`) is found only by trial and error.
  - Gate check names have no table part, so the same check on the same column in two tables would collide.
  - The worked example breaks the spec's own `registry_evidence` rule.
  - The Mapping Document hides `from: document` and does not mark `cik` as the record key or show `kind_values`. It says only "from `entity_type`", so the fact that only `operating` becomes a Company is invisible there.
  - 89% of the family maps away from MDM. That is correct per §13.4, but a Company source that masters 11% of its family probably wants a kind rule rather than an allow-list (§13.4 item 6).
