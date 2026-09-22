# Trial log: onboarding `iapd.adv_adviser`

## Questions

1. **How do I parse a US-ordered timestamp (`03/17/2026 11:29:59 AM`)?** Looked in §9 (`date_prefix` needs a leading `YYYY-MM-DD`; `timestamp` needs ISO 8601 and "the prototype accepts any text"). Neither primitive fits. Assumed a Custom Step (§11 value step) is the right tool, and wrote `adv_submitted_date@1`. It returns an ISO date only because IAPD states no time zone (gap G4). Resolved by reading, not by a runner error. Open point: a `date_format:` argument on `date_prefix` or `timestamp` would remove the only Custom Step. The mm/dd/yyyy format seems common enough to count as a Named Convention.
2. **What does a `date` silver column accept: an ISO string or a date object?** Looked in §12, which gives only the type names. Assumed an ISO `YYYY-MM-DD` string. The type check passed on all 17,413 rows, so the runner result answered it, not an error message.
3. **Does the CSV reader give `""` or "missing" for an empty cell?** Looked in §8.1, §8.3 and §9. §8.3 says a missing path gives `default`, but a CSV cell that exists and is empty is not "missing". Assumed `""`, and chained `empty_to_null` on every optional text column. The case expecting `office_city: null` passed, which is consistent with that. `int` on `""` gives `default` ("not a whole number"), so AUM needed no chain.
4. **What identifier namespace and format should CRD use?** Looked in §13.1: "Only `sec_cik` exists as a format (gap G3)". Assumed namespace `crd` with no `identifier_formats`. No zero-padding convention is known for CRD, so values stay as written (`79`, `336316`). No runner error.
5. **Can silver be one row per filing when the MDM record key (CRD) repeats?** Looked in §13.2 ("the silver table must already be one row per MDM subject") and §12 (the collapse grammar is Open, §25 item 6). This is a real conflict. The task asks for one silver row per filing, and CRD 19258 files 15 times in March alone: 2,628 CRDs repeat across the batch. I kept one row per filing (key `filing_id`) and declared no `collapse`. The runner raised nothing, and a merge case shows two filings of one CRD giving a single `binding_required` record. Unresolved: whether the Merge Stage treats the later row as a patch, and in which order.
6. **Should the `1F1-Country` column feed MDM `country`?** Looked in §13.2a. IAPD writes country names (`United States`, `Taiwan,  Republic of China`), while GLEIF writes ISO codes (`US`). Following the §13.2a rule, I kept it as evidence (`office_country_name`) and mapped no country. No runner error.
7. **Should `name` be mapped when the policy does not rank `iapd.adv_adviser`?** Looked in §13.2a and `policies/mastering-policy.yaml`. Assumed yes: the name means the same thing as other sources' names, and mapping it now costs nothing. The Mapping Document confirms it stays "evidence only" until a policy version ranks IAPD. No error.
8. **What goes in `dataset.contract.family` for IAPD?** Looked in §13.3: "the Clean MDM source-registry family … checked at registration". The sandbox has no registry to check against, so I guessed `adv_base`. Nothing validated it, because registration is not prototyped. Also unclear: whether `effective_time: unknown` is right for a source nobody ranks (§13.3 says "needs nothing here").
9. **Is `evidence_only` enforced?** Looked in §15, which says "Not prototyped". I checked by putting `legal_name` (which *is* mapped) into `evidence_only` as a deliberate mutation. The runner accepted it silently. A reviewer reading the case would believe it is checked. It should be refused or flagged as not enforced.
10. **Does the `where`/`has` filter or `from: document` matter for CSV?** Looked in §8.4. Assumed `each: "."` gives one row per CSV row, as for JSONL. It worked (7 rows from 7 fixture rows).
11. **Does a check need an explicit gate limit?** Looked in §16: "every check defaults to 0". Only `rows` needs a `min`. I added an explicit `check.pattern(office_state): { max: 0 }` to confirm that a named limit is accepted. It was.
12. **How does a Custom Step import the API?** §11 says `from source_contract import …`. `engine/source_contract.py` re-exports from `source_engine`, and the import worked without a `requires` (standard library only).
13. **Where should the fixture CSV live, and must it keep the original bytes?** Looked in §5 and §15. I cut the header plus 7 whole original lines (CRLF endings kept) into `fixtures/march-2026-seven-rows.csv`.
14. **Merge cases and Docker.** Looked in §15 and §4.1. `docker info` worked through the Colima socket (`DOCKER_HOST` exported), and the merge case passed. I could not tell from the spec whether the runner needs `DOCKER_HOST` set or finds Colima itself.

## Errors met

No unintended non-zero exit from `./source`. The contract validated and all 5 initial cases passed on the first run.
- A deliberate mutation run (AUM expected `0` instead of `null`, plus a wrong `evidence_only`) reported one located case failure. It gave JSON pointer `/tests/3/expect/silver/iapd_adv_filing/4`, line 134, with the diff and the fixture. State was `draft`, and I did not capture the exit code. The wrong `evidence_only` was **not** reported (Question 9). I restored the contract.
- `./source prove` without `--gate` exits 0 with state `draft`, which is §25 item 2's open issue: an agent must read the state, not the exit code.

## Files read (in order)

1. `SPEC.md`
2. `families.local.yaml`
3. `source` (the runner wrapper script)
4. `sources/gleif/contract.yaml`
5. `sources/gleif/MAPPING.md`
6. `policies/mastering-policy.yaml`
7. `sources/gleif/fixtures/three-records.jsonl` (first 600 bytes)
8. `engine/contract.schema.json`
9. `engine/source_contract.py`
10. `data/adv-base/IA_ADV_Base_A_20260301_20260331.csv` and `data/adv-base/IA_ADV_Base_A_20260801_20260831.csv` (headers, then profiled with a stdlib `csv` script)
11. `sources/adv-adviser/fixtures/march-2026-seven-rows.csv` (my own cut, re-read to confirm the rows)

Nothing else under `engine/` was opened.

## Result

- **State: `version proven`.** `./source prove sources/adv-adviser --gate` exits 0.
- `contract.yaml`: 164 lines. `custom.py`: 17 lines (1 value step). Custom fraction: 1 of 15 columns (6.7%).
- **6 Named Cases:**
  1. an ordinary filing, with silver and MDM expectations;
  2. trap: a private-residence main office has blank address fields, read as null;
  3. trap: `1N`=Y but `1N-CIK` is blank on all 20 public-reporting rows, so the CIK is useless as an identifier;
  4. trap: no regulatory AUM (`5F1`=N) gives a blank `5F2c`, read as null and not 0;
  5. trap: one CRD, many filings;
  6. a merge case: a declared binding gives `bound`, and unbound CRDs give `binding_required`, including the repeated CRD giving one record. It needs Docker, which worked.
- **Gate** over `iapd.adv_base_filings` (2 artifacts, batch `25033bf4a39f`): rows 17,413 (floor 17,413); rejected, type_errors and deferred all 0; all 7 checks 0 violations (`not_null(crd)`, `not_null(legal_name)`, `unique(filing_id)`, `pattern(crd)`, `pattern(sec_file_number)`, `pattern(office_state)`, `row_count`).
- `MAPPING.md` was generated by `./source mapdoc`.
- **Harder than it should be:**
  - No date primitive for a non-ISO date: a trivial reformat needed Python.
  - The spec's rule that silver is one row per MDM subject contradicts a one-row-per-filing source, and the collapse grammar is Open.
  - `evidence_only` is silently accepted but not enforced.
  - "Cases passed" exits 0 like "proven".
  - Nothing tells the author what `dataset.contract.family` must be for a new provider.
