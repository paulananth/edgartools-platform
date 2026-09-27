# SEC place codes: one reference table in rules/

Type: task
Status: claimed (Claude, branch `claude/rules-08-place-codes`, 2026-09-26 20:02 ET)
Blocked by: none

## Outcome

Operator, 2026-09-26:
- "find state_inc refrence data from sec";
- then "yes" to building it as one table in `rules/`.

SEC's EDGAR state and country codes (`stateOfIncorporation`, and each
address's `stateOrCountry` and `countryCode`) are one reference table,
`rules/reference/sec-place-codes.yaml`:
- all 309 codes, as edgartools 5.30.0 ships SEC's list;
- the place SEC names for each, and its type (US, CANADIAN, FOREIGN or
  UNKNOWN);
- its ISO 3166 code, the way GLEIF writes a jurisdiction.

`names.edgar_jurisdiction` reads that table instead of carrying its own copy.

## Checklist (times ET)

- [x] `/gof-refactor-reviewer` on `names.py`, `matching.SEC_CODES` and
  `company_source._business_addresses` (2026-09-26 20:03 ET).
  - **Verdict:** move as-is. `names.py` has one commit, and the table has
    never changed.
  - **Noted:** the SEC reader calls `edgar_jurisdiction` directly, outside
    the `SEC_CODES` registry. So a change to the table changes SEC records.
- [x] Found the full list without an SEC request (20:01 ET): edgartools'
  `edgar/reference/data/place_codes.csv` (sha256 `1daf0cc6…ab14`), 309 codes.
  The old table covered 169 of them, and all 169 are in the list.
- [x] ISO codes for the 140 codes the old table lacked (20:05 ET).
  - **Drafted** by country name with `pycountry`, as a one-off `uv run --with`
    tool that is not a dependency.
  - **Checked by hand:** 13 corrected (CA-PE, CA-YT, US-MP, US-AS, FM, MD, PS,
    CV, IR, KP, LY, MO, CD).
  - **Unplaced:** only `XX` ("unknown").
- [x] **Rebuild, not legacy** (operator, 20:06 ET: "we are completely
  rebuilding edgartools there is no more production or legacy this is it").
  So there is one table, with no frozen copy of the old 169 codes.
- [x] What changes, measured over the 2026-09-24 bronze scan of 76,230 filers
  (20:10 ET).
  - **Codes:** 182 distinct codes appear. 11 of them were unplaced before
    and are placed now: Z5, N5, 1B, Z0, E3, 2Q, J0, P0, F6, X2, B6. All 11
    appear only in address `countryCode`, never in `stateOfIncorporation`.
  - **Filers:** 19 filers are touched.
  - **Companies:** 3 Companies' SEC address country goes from unknown to the
    right country.
    - Deswell Industries (Macau): the name rules still defer it. It has no
      postcode and no state of incorporation.
    - CL Workshop Group (Macau) and Kandal M Venture (Cambodia): the name
      rules find no GLEIF record for either.

    No match outcome changes.
  - **Still unplaced in bronze:** `XX` (23 values) and `I9` (1 value, not in
    SEC's list).
- [x] `names.py` reads the table through `rules_files.reference`. The US
  territories now also include MP and AS, which the new table writes as
  US-MP and US-AS (20:12 ET).
- [x] Tests (20:18 ET).
  - `tests/mdm/test_sec_place_codes.py`:
    - the table equals SEC's list as edgartools ships it;
    - every code has an ISO code except `XX`;
    - the 169 codes placed before read the same (digest `51f54ac5…`);
    - newly placed codes resolve;
    - a US territory agrees with its own country code.
  - 202 targeted tests pass: names, matching, Company source, Company
    address, the rules files and the image layout.
- [x] Three-axis `/code-review` (finished 2026-09-27 01:41 ET, by `date`).
  - **The main finding, from all three axes:** the table sat outside the
    policy's digest, so an edit to it would change matches and SEC Company
    records under the approved fingerprint `983352e8…`.
  - **The fix:** `files.policy()` now carries every `rules/reference/` table
    in the policy body, so the digest pins it. The name stays `edgar-iso-v1`,
    and its content is now pinned by the policy digest. Renaming it to v2
    would have changed both name rules' bodies under their unchanged version
    labels.
  - **Fingerprints:**
    - the new policy digest is `3520e890d46020e1c0a579807151b9d1cadcf5adab535172811b8e96f99b1e17`;
    - without the `reference` section it is still `983352e8…4049`;
    - `name_matching_policy(active=True)` is `ad70680a…`.

    Pinned in `test_rules_config_digests.py`, `test_clean_activation.py` and
    `test_clean_four_companies.py`, each also checking the old value without
    the table. **Merging needs the operator's approval of `3520e890…`.**
  - **Also fixed:**
    - the YAML header now says 156 codes were seen plus 13 US codes, that 11
      of the new codes occur in bronze, and names the territories;
    - the test constants are renamed (`PRE_MOVE_CODES`);
    - the edgartools drift test checks the list's sha256 first and says what
      to do when it changes;
    - a territory drift test;
    - `pending-proofs.yaml` notes that the proofs were measured with the
      169-code table and that none of the 3 touched Companies is in their
      files (checked before 01:41 ET).
  - **Evidence:** `.scratch/rules-skill/research/08-place-code-impact.py` and
    its output `08-place-code-impact.json` reproduce the 182 / 11 / 19 / 3
    counts. The inputs are `cm08-sec-scan.jsonl` (`bdf379bf…`) and
    `cm08-coverage-2.jsonl` (`97e5d118…`).
  - **Tests:** 288 affected tests pass.
- [ ] Operator approves policy digest `3520e890…`; PR and CI.

## Follow-up (not in this ticket)

Company mastering ticket 18, item 5: the SEC reader copies the raw code into
the address region (ASML: `P7`). With this table the reader can put the
country (`NL`) in the country and leave the region empty. That is a reader
change, and it changes SEC Company records.
