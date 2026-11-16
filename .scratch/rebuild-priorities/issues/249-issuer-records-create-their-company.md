# 249: A GLEIF record that an N-PORT holding names as its issuer creates its Company

Type: task (configuration only; no code change). Status: open. Blocked by: none. Related: ticket 22 (the first ruling and its duplicate finding), ticket 248.

## Ruling

Operator, 2026-11-16: "Fix A yes". The common stock Securities whose N-PORT filing states an issuer LEI (10,177 of the 18,376 with no Company) wait because the issuer's GLEIF record is not a Company (9,909 records wait, all unbound). The issuer rule `gleif-issuer-lei` creates the Company when none holds the LEI. This reverses "Issuer joins, never creates" (operator, 2026-10-16, after 3,240 duplicate Companies).

## Why the first version failed, and the guard

Identifier rules run before name rules in one merge, so an issuer that is also an SEC filer became a second Company (3,240 of 3,528 name-paired issuers). In the hosted store the SEC-GLEIF name pass has already run (2,042 pairs held), so only issuers it did not pair would create. 993 of the 9,909 waiting issuer records have a normalized name equal to an SEC filer's name: they are likely the same company, so they are held for review, not created.

## Parts

- [x] 2026-11-16 10:17 ET Ruling recorded and evidence counted (hosted counts, 2026-11-16).
- [ ] A test on a disposable store that fails first: an issuer no Company holds creates one; an issuer that joins by the SEC-GLEIF name pass first stays one Company; a look-alike by name is held for review.
- [ ] `gleif-issuer-lei` as a creating version (`on_no_match: mint`) by configuration, and the guard for the 993 (a looser name pass or a review), proved on a disposable store with the name pass applied first.
- [ ] Mapping Documents regenerated; policy digest fixtures updated (`policy_layers`).
- [ ] Hosted: switch-on needs the operator's word.
- [ ] Learning → skill.
