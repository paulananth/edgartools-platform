# Refining log: sec.submissions.company, business postcode check (trial, 2026-09-30)

Skill: refining-rules, mode **change-quality**, then **test**. The operator was not reachable, so every question below is ASSUMED. Nothing was approved, saved, recorded, activated or published. No database was used and no network requests were made. The repo was not edited: `git status` was clean afterwards.

## Request
"Add a data quality check to the SEC Company feed that flags a Company whose business address has no postcode, and tell me how many records it would flag."

## Steps
1. **Identify.** `rules/sources/sec.submissions.company/source.yaml` exists, so this is refining-rules. Read `quality.yaml` (`sec-company-quality-v1`: 3 fixes, 4 checks). No run reports were available, so the counts below were measured.
2. **Draft.** Copied `rules/` to `work2/rules`. In `quality.yaml`:
   - added `business_postcode_present` (`present@1`, `value: fields.address.postcode`, `on_fail: flag`);
   - bumped the version to `sec-company-quality-v2`.

   The entry was added with a text edit, so the file's comments survived (`files.dumps` would have dropped them). `quality.check_quality` passes, and `files.source(..., root=)` loads.
3. **Pin.** `batch_hash` = sha256(receipts.jsonl) = `b8553e6f16bd758239bff49187d83420c79de47c954abd09aed4dff0aa06b446`. All 7,001 files (7,000 submissions plus 1 ticker catalog) matched their sha256 and byte counts; 0 mismatches. A key `warehouse/bronze/X` maps to `<capture>/bronze/X`.
4. **Rows.** Each row was built from:
   - `stage_company_loader(...)[0]`;
   - the business row of `stage_address_loader` → `company_source.business_address` (None if absent);
   - `forms` = sorted distinct `filings.recent.form`;
   - **plus `tickers` from the capture's `company_tickers_exchange.json`**. The classification rule reads `ticker` → `tickers`, and the skill's recipe omits it.
5. **Counts.** This was a full pass over all 7,000 documents, not a sample. It took about 18 minutes of wall time on this disk (42 s of CPU, so the time went to I/O).

| | All filers (`mapped_values`) | What MDM receives (`normalize`) |
|---|---|---|
| Records | 7,000 | 6,414 (586 deferred: `classification_deferred`) |
| **Flagged: business_postcode_present** | **659** | **403** |
| – US address, no postcode | 78 | 77 |
| – foreign address, no postcode | 322 | 320 |
| – no business address content at all | 259 | 6 |

Other quality counts on what MDM receives, unchanged from v1:
- `fixed:standard_address` 5,588;
- `fixed:state_from_name_tag` 11;
- `fixed:dc_state_is_empty` 4;
- `withheld:matching.address` 6.

**Before and after, record by record, on what MDM receives.** Both versions give the same 6,414 records. 403 of them gain the flag, and 0 differ in any other way (fields, fixes, withheld). The quality `version` is inside the hashed body, so every record's fingerprint changes. That is why the new version applies to new batches only.

**Controls (made-up TEST INPUTS):**
- a US address without a postcode is flagged;
- an address with a postcode is not flagged;
- no business address is flagged.

**Examples of what MDM receives:**
- 0001000694 NOVAVAX INC (MD, US);
- 0000100493 TYSON FOODS (AR, US);
- 0001007587 KVH INDUSTRIES (RI, US);
- 0001004156 ARAUCO (CL);
- 0001005516 BOS (IL);
- 0001009001 CAMECO (CA);
- 0001015650 SK TELECOM (KR);
- 0001023514 HARMONY GOLD (ZA);
- 0001024672 ELTEK (IL);
- 0001026785 HIGHWAY HOLDINGS (CN).

The full list is in `measure.json`.

6. **Metadata.**
   - `rules mapdoc write --only sec.submissions.company --root work2/rules` exited 0, and the workbook in the copy changed.
   - `rules mapdoc check --root work2/rules` exited 0.
7. **Test.**
   - Draft digest: `c9317f96e66d756cd0b53f36646a21d203e7e2e25bc74635ffff92f9aa200ee0` (the repo's is `fc643704…40d1`).
   - Proof: `work2/proof.json`, sha256 `9325e760…bf2e`.
   - Version label: `sec.submissions.company-2026-09-30.postcode-flag`.
   - STOPPED by the trial rules before `rules save` and `rules record-proof`. This is not a skill gap.

## Questions (ASSUMED)
- **Q1.** What should happen when the postcode is missing: exception, withhold or flag?
  - Recommendation: `flag`. The operator said "flags", and 320 of the 403 are foreign addresses that may legitimately have no postcode, so withholding or setting them aside would hurt.
  - ASSUMED: flag.
- **Q2.** Should a record with no business address at all count as "no postcode"?
  - Recommendation: yes. It is 6 records in MDM, and a separate `present@1` on `fields.address` would be needed to split them out.
  - ASSUMED: yes, reported separately.
- **Q3.** Should the check read the address as SEC wrote it (`fields.address.postcode`) or the standardised copy (`matching.address.postcode`)?
  - Recommendation: `fields`. It is the value MDM shows, and the standardising fix never blanks a postcode, so the counts would be identical.
  - ASSUMED: fields.
- **Q4.** Should foreign addresses be excluded from the check?
  - REFERENCE.md has no conditional check, so this cannot be expressed today.
  - ASSUMED: include them and report the split.

## Guesses and test inputs
- The ticker catalog was zipped into per-CIK tickers the way `_catalog_tickers` does it, in catalog order, not by source_rank.
- `publication` for `normalize` was per file: `artifact_sha256` = the file's sha256, `member` = its receipt key, `publication_key` = "dry-run", `revision` = 0.
- The three controls above are made-up test inputs.

## SKILL-GAPs
1. "For SEC submissions, build one row per file from the repo's own loaders: … `forms` from `filings.recent.form`." The list leaves out `tickers`, which the classification rule reads (`ticker: [tickers]` in company.yaml). Without it, the "What MDM receives" count is silently wrong. Fix: add "`tickers` from the capture's company_tickers_exchange.json, as `_catalog_tickers` does".
2. "A receipt key such as `warehouse/bronze/submissions/…` maps to `<capture>/bronze/submissions/…` (drop the `warehouse/bronze/` prefix)." It is ambiguous: dropping the prefix alone gives a wrong path. Fix: "replace the `warehouse/bronze/` prefix with `<capture>/bronze/`".
3. "Read and write rules files only through `edgar_warehouse.rules.files` (`load`, `source`, `dumps`, `write_source`)." `dumps` drops the comments in `quality.yaml`. Fix: say to add an entry by text edit, then verify with `files.source`.
4. "`adapters.normalize(...)`, as in data-onboarding **test**." The skill gives no `publication` for one-file-per-record captures, and no shape for the deferred list that `quality.counts` takes. Fix: give both.
5. There is no guidance on whether "no address" counts as a missing component (`present@1` on `fields.address.postcode` fires on both), or how to scope a check to US addresses. Fix: note it, and log conditional checks as new code.
6. "The log: `.scratch/onboarding/<source>/refining-log.md` on your branch." There is no sandbox or trial alternative, unlike data-onboarding's "Where you write". Fix: mirror that section.
7. The skill gives no runtime expectations. A 7,000-file pass took about 18 minutes of wall time, and `mapdoc write` took more than 10 minutes. Fix: state the expected times, or suggest a bounded sample first.
