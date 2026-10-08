# Configured census reading

Goal: retire executable source-specific parsing while preserving whole-source
Company census and MDM semantics. This ticket advances the census path; the
full skills/parser goal remains incomplete until every remaining gate passes.

- [x] Review live ownership, callers, history and GoF costs before edits; dedicated Codex tree, live guard passes, two historical census commits and focused GoF review. 2026-10-08 07:16 ET
- [x] Add bounded generic value iteration and exact text shape checks; 141-case full native suite passes, source count checked before cloning/selection. 2026-10-08 07:16 ET
- [x] Express GLEIF census identity, legal/other names and conditional registration reads in bundled Rules; old _text, _other_names and sec_keys exist only in test support, actual caller uses native Rules. 2026-10-08 07:16 ET
- [x] Verify counts, branches, former/other names, timestamps, cascade and refusal order against the historical implementation: 97 targeted cases pass in 8.43s, including deliberate key corruption and paired malformed inputs. 2026-10-08 07:16 ET
- [x] Qualify authenticated captured records and deliberate faults through the actual caller: 1,000 SEC captures plus 1,000 GLEIF records, 1,000 separately identified synthetic filers, exact historical census equality, 59.22s; runtime pins in captured-parity.json. Repackaged sampled EOF only. 2026-10-08 07:16 ET
- [ ] Verify installed bundle and restricted PostgreSQL 16 publication/recovery boundaries.
- [x] Run local MDM and engine tests after final fixes: 1,303 passed, zero skips, 156.93s; independent two-axis review has no scoped blocker (REVIEW.md). 2026-10-08 07:18 ET
- [ ] Commit, run full CI and open a PR.
- [x] Reconcile parent issue 20 and executable caller inventory against merged main 862a1e66 and the open #866 documentation PR; remaining paths are listed below. 2026-10-08 07:16 ET
- [ ] Whole-source configured census construction, Company preparation/census/provenance retirement, GLEIF release/semantic retirement, record mapping retirement, full 6,414 Company / 3,052 CIK+LEI replay/recovery and configured capture remain required by the parent goal.

Design review: name_census.py changed only for the original matching and cascade
rules (#713, #746), so no class hierarchy is justified. The current cost is
source-specific JSON extraction and normalizer application in an executable
callback. Use the existing interpreter and plain functions; added generic
iteration and shape checks cost grammar validation and independent tests.

## Review findings and qualification boundary

The two independent review axes found eager other-name reads on excluded
records, rejection of empty other-name containers, premature registration
reads on unwanted legal names, and moved refusal order for paired faults.
Selective configured phases preserve the historical order. Historical
malformed containers raise AttributeError; the configured reader refuses
with typed SourceRejected. Both stop construction, with no partial census
publication. This exception-class boundary is explicit, not arbitrary-input
identity or whole-source qualification.

## Remaining parent goal inventory

- `company_source.py` still implements landing receipt/provenance, preparation,
  census filers, cascade filers and write_name_census; the active Company CLI
  still imports and calls it. The new recipes retire census extraction only.
- `name_census.py` still aggregates source populations and cascade decisions;
  this bounded sampled construction does not qualify whole-source construction.
- `gleif_source.py` still validates archive/release semantics and constructs
  record evidence. Native framing and configured fields do not retire it.
- `adapters.py` still implements classification, record keys, matching,
  provenance, scopes and links. Configured fields alone do not retire mapping.
- Person fixture conversion was deleted by #816; do not restore it. Parent
  issue 20's L5/20d checklist is older than that evidence.
- Parent L3-L8 stay incomplete as whole requirements. `provider.capture`
  has no registered configured worker, so `sec_client.py` must remain.
- Installed empty restricted PostgreSQL16 qualification on the full 6,414
  Company / 3,052 CIK+LEI population, unchanged replay and recovery is still
  required. The installed test here qualifies two Company/two Person rows.

No source digest is activated, no deployment is performed, and no SEC
request is made by this change. Complete source-version approval and the
remaining parent goal gates remain necessary.
