# Person and link quality rules

Priority: 10, tier 2, the recreation proof. Map: [Rebuild priorities](../map.md). Moved from `.scratch/mastering-to-done/issues/18-person-and-link-quality-rules.md` on 2026-10-13; a Blocked by list of numbers now uses this map's numbers (or names the old effort); free text keeps the old effort's numbers.

Type: task (configuration, then code for the run report)
Status: open
Blocked by: mastering-to-done 03, mastering-to-done 14

## Question

Build ticket 03's checks:
- Person's critical checks in `rules/sources/sec.submissions.person/quality.yaml`, with tests on names with accents, apostrophes, degrees and footnote marks;
- the link checks, with the Person link engine (ticket 14);
- the three run report checks, reported and never blocking. This needs code: the GoF consult first.

The quality versions change, so each needs a test run and the operator's approval.

## Checklist

Plan (2026-10-14 13:55 ET): two PRs. The first holds the critical checks (configuration plus one adapter rule); ticket 11's proof starts once it merges. The second holds the run report checks (code).

- [x] Measured on the local copies (`.scratch/onboarding/sec.submissions.person/measure_quality.py`, `measure-quality.json`, counts only), 2026-10-14 13:40 ET: 31,097 Person filers (submissions) and 9,313 ownership owner rows. None has an empty name, a name with no letter, a letter outside ASCII, a curly apostrophe or a footnote mark; the four director-or-officer names with digits are firms (an LP, two L.P.s, an L.L.C.). No owner row that holds a capacity lacks its issuer CIK or its period of report. So the checks set nothing aside today; they guard later deliveries. (The degree and suffix counts there are upper bounds: the measuring pattern has no word boundary.)
- [x] GoF consult on `adapters._link` (2026-10-14 13:55 ET): leave the structure; `ends` is one opt-in rule beside `interval` and `status` (the capacity branch was consulted on 2026-10-13 with the same verdict)
- [ ] Person CIK present and 10 digits: the record key (`sec_cik`, submissions) and the identifier format (`sec_cik`, ownership) already set a bad CIK aside (`invalid_cik`, `missing_record_identity`); made non-blocking in both contracts, as the ruling says it never stops the run
- [ ] The name has letters, in both Person contracts: `pattern@1` (a Unicode letter), `on_fail: exception`; tests on invented names with accents, curly apostrophes, degrees (kept as filed) and names with no letter (set aside)
- [ ] ~~Drop footnote marks~~ not built: no name in either feed carries one (measured above); the proxy parser that met them was deleted (#764). Filing text (ticket 31) brings it back if DEF 14A names return
- [ ] Link: both ends present: `ends: {reason}` on a relationship mapping sets aside a record whose link names no end (adapter code, opt-in; without it a list item with no end is still no link); on the three ownership links
- [ ] Link: capacity from the allowed set: the capacity is fixed text in each mapping, so a test holds every contract's capacities to its type's `capacities` in `rules/merge/relationships.yaml`
- [ ] Link: start no later than end: `interval: {reason}` on the three ownership links (a capacity link's start is its date; folded periods end after they start by construction)
- [ ] Every new set-aside reason is non-blocking in its contract (test)
- [ ] Digests of the changed contracts and quality versions, explained in plain words; pinned digest tests updated
- [ ] Ownership Proving Run on the new rules, and the full installed proof (contract code changed)
- [ ] Three-axis review, PR, CI, merge on the operator's word (PR 1)
- [ ] Run report checks (PR 2): per source, row-count change from the last run, empty-value rate per field, age of the newest record (unknown where the feed states no time); reported, never blocking; GoF consult first
