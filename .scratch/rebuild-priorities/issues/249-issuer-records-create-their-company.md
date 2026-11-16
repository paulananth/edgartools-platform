# 249: A GLEIF record creates its Company (configuration only)

Type: task (configuration only; no code change). Status: open. Blocked by: none. Related: ticket 22 (the first ruling and its duplicate finding), ticket 248.

## Ruling

Operator, 2026-11-16: "Fix A yes". The common stock Securities whose N-PORT filing states an issuer LEI (10,177 of the 18,376 with no Company) wait because the issuer's GLEIF record is not a Company (9,909 records wait, all unbound). The issuer rule `gleif-issuer-lei` creates the Company when none holds the LEI. This reverses "Issuer joins, never creates" (operator, 2026-10-16, after 3,240 duplicate Companies).

## Ruling widened (operator, 2026-11-16: "I am reversing 2026-10-16 rule that GLEIF only joins, never creates. GLEIF can create company no new code only config")

The reversal is not limited to issuers: GLEIF may create a Company, by configuration only, no code change. The configuration has two scopes, and the scope is the next decision:

- **Issuers only:** the creating rule keeps its test that an N-PORT holding names the record as its issuer (9,909 waiting records; resolves up to 10,177 Securities).
- **Every eligible GLEIF entity:** the test is dropped. A 3% sample of the 3,041,042 waiting records is 56.6% ACTIVE and ISSUED, 36.7% ACTIVE and LAPSED, 6.5% INACTIVE and RETIRED, so about 1.7 million records are active and issued. Companies would grow from 26,260 to about 1.7 million (about 65 times), and each would need the duplicate guard below.

## Scope ruled (operator, 2026-11-16: "every eligible GLEIF entity now")

Every eligible GLEIF entity creates its Company now, with no issuer test. Eligible is the test the SEC-GLEIF name rule already states (`gleif_entity_eligible@1`): category GENERAL, entity status ACTIVE, registration status not ANNULLED or DUPLICATE. A registration that is LAPSED is therefore eligible. From the 3% sample that is about 93% of the 3,041,042 waiting records, about **2.8 million Companies** (26,260 today, about 110 times more), not the 1.7 million first written (that counted ISSUED only).

## Why the first version failed, and the guard

Identifier rules run before name rules in one merge, so an issuer that is also an SEC filer became a second Company (3,240 of 3,528 name-paired issuers). In the hosted store the SEC-GLEIF name pass has already run (2,042 pairs held), so only issuers it did not pair would create. 993 of the 9,909 waiting issuer records have a normalized name equal to an SEC filer's name: they are likely the same company, so they are held for review, not created.

## Design (found 2026-11-16, configuration only)

1. **The creating rule.** A rule `gleif-lei` in `rules/merge/kinds/company.yaml`, family `binding`, source `gleif.level1.v1`, `on_no_match: mint`, tests `identifier_match` and `identifier_cardinality` on `lei` (the shape of `company-cik`), switched on in `rules/merge/policy.yaml`. The `lei` Identifier Contract already names `gleif.level1.v1`.
2. **Eligibility cannot be a matching test.** `gleif_entity_eligible@1` belongs to the name-binding family only. A binding rule cannot test ACTIVE or ANNULLED, so the status gate goes into the kind decision: a Dataset Contract states a `kind_field` or names a `classification` rule, never both (ADR 0015). GLEIF's contract changes from `kind_field` to a classification rule `gleif-company-candidate`: GENERAL and ACTIVE and registration not ANNULLED or DUPLICATE is a company; a FUND, BRANCH, government or international organization is deferred with its probable kind (as `kind_values` and `probable_kind_values` do today); anything else is deferred. This needs the record to carry the entity category as a field (to confirm).
3. **The duplicate guard.** The SEC-GLEIF name pass gives an SEC Company the GLEIF LEI first, so the GLEIF record then joins by LEI instead of creating. SEC filers that pass did not pair would duplicate: 993 of the 9,909 issuer records have an SEC filer's name. The guard is still open: a looser name pass (measured), or review.
4. **Every record is reprocessed.** The change alters GLEIF's rules, so all 3,043,084 GLEIF records load again (and about 2.8 million Companies are created, with their lookups and links). That needs the operator's word to run, and a measured time first.

## Built (operator, 2026-11-16: "I don't want custom code all must go through engine", then "Yes")

- The creating rule `gleif-lei` and its switch-on (`kinds/company.yaml`, `policy.yaml`).
- The kind rule `gleif-company-candidate`: GENERAL, ACTIVE, registration not ANNULLED or DUPLICATE is a Company; fund, branch, government and international organization are held back with their probable kind, the rest with none. It reads GLEIF's own raw paths, so the reading is unchanged. A LAPSED registration of an ACTIVE entity is a Company.
- **The engine:** `link_matching_records` (Rust, `record_matches.rs`) takes `name_paired`, the subjects a name rule holds a pair for; such a subject waits for the name rule and never creates. The merge passes it with one call (`_name_paired`); the rule order stays in the engine.
- The load chain: `adv-custodians-06` and `-03` follow `gleif` (a rule that mints by LEI now has a second minting source), and `adv-mastering-03` waits for `nport-registrant` in their place.
- Tests that waited for GLEIF now use an adviser filing (a rule that waits); the recorded GLEIF mapping outcomes changed on purpose (`valid`, `non_company`).

## Known limit (kept visible in `test_the_pass_pairs_and_the_merge_joins_the_company_when_the_pair_comes_first...`)

A GLEIF record that arrives before its SEC filer is paired creates its own Company, and a name rule cannot join it afterwards (it binds a record that waits; a binding rule cannot merge two Companies). A load pairs first, so a load is not affected. A filer registered after its GLEIF Company exists would duplicate. Merging the two would be a second engine change (a name rule with a merge outcome).

## Parts

- [x] 2026-11-16 10:17 ET Ruling recorded and evidence counted (hosted counts, 2026-11-16).
- [x] 2026-11-16 10:37 ET Scope ruled: every eligible GLEIF entity.
- [x] 2026-11-16 11:11 ET Tests that failed first: `test_a_gleif_record_creates_its_company_or_joins_the_one_holding_its_lei` (no Company created), `test_a_record_a_name_rule_holds_a_pair_for_never_creates_and_the_others_still_do` (`ValueError: too many values to unpack`: two records created), `test_only_an_active_general_entity_whose_registration_stands_is_a_company`. A filer paired first, then its GLEIF record, is one Company.
- [x] 2026-11-16 11:11 ET The creating rule, the kind rule and the engine input (above); mastering tests pass on PostgreSQL (84) and MySQL (82, 2 skipped), 2,274 mdm, engine and architecture tests, the Rust tests.
- [ ] The 993 issuer records whose name equals an SEC filer's name, and every filer the name pass has not paired to its GLEIF twin, would still create a duplicate: measure on a disposable store, then a looser name pass (configuration) or review.
- [x] 2026-11-16 11:11 ET Mapping Documents regenerated (`company`, `gleif`); the company mastering fixture's policy digest updated (`tests/integration/test_company_mastering_target_postgres.py` passes).
- [ ] Hosted: needs the operator's word to run. It changes GLEIF's rules, so all 3,043,084 records load again and about 2.8 million Companies are created, with their lookups and links. Time not measured. The Rust extension must be rebuilt where the load runs.
- [ ] Learning → skill.
