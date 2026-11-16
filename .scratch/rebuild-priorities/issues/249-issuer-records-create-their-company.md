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

## Parts

- [x] 2026-11-16 10:17 ET Ruling recorded and evidence counted (hosted counts, 2026-11-16).
- [x] 2026-11-16 10:37 ET Scope ruled: every eligible GLEIF entity.
- [ ] A test on a disposable store that fails first: an issuer no Company holds creates one; an issuer that joins by the SEC-GLEIF name pass first stays one Company; a look-alike by name is held for review.
- [ ] `gleif-issuer-lei` as a creating version (`on_no_match: mint`) by configuration, and the guard for the 993 (a looser name pass or a review), proved on a disposable store with the name pass applied first.
- [ ] Mapping Documents regenerated; policy digest fixtures updated (`policy_layers`).
- [ ] Hosted: switch-on needs the operator's word.
- [ ] Learning → skill.
