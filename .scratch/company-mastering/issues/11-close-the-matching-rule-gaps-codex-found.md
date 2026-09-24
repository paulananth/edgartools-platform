# Close the matching-rule gaps the Codex review found

Type: task
Status: in progress
Blocked by: 04

## Question

A read-only Codex review of the merged tickets 03, 04, 09 and the warehouse
"other" fix (2026-09-24, 18:00 ET) found three gaps that no ticket tracked.
The operator asked for one follow-up ticket for them (2026-09-24 18:20 ET):

1. **A GLEIF record could create a Company.** Registration never required a
   matching rule that creates a Company (`on_no_match: mint`) to belong to the
   identifier's issuing source. An activated GLEIF rule set to `mint` would
   create a Company from an unmatched LEI, where the operator decided an
   unlinked GLEIF record waits in the Stage.
2. **A hand-matched record could make a crosswalk within one batch.** When a
   caller binds an SEC record that also carries an LEI, `binding.propose`
   counted that LEI as held by the Company, so a GLEIF record in the same batch
   joined through it. Q14: an LEI never becomes a CIK crosswalk merely because
   both values appear on one record. Across batches the rule already held.
3. **Shell and ASML cannot become Companies on the standard SEC contract.** It
   still maps only `entity_type = operating` to Company; the candidate
   classification rule that accepts `other` with an industry code lives only
   in the four-company test.

## What gap 3 needs, and why it stays open here

The candidate classification rule (step 2: SEC `other` with an industry code
is a Company) now lives in the Company policy as data, version
`2026-09-24.2`, instead of only in a test. **It is not switched on, and Shell
and ASML still wait in the Stage on the standard SEC contract.** Pointing the
SEC contract at the rule would, until the rule is activated, hold back *every*
SEC record, Apple and Microsoft included, because an unactivated verdict is
deferred. Activation needs the proving run (ticket 05) and the operator's
approval of the digest (ticket 06). The switch moves there.

The version is new because the rule gained a `source`: §10 check 9 refuses one
rule version with two bodies.

## Checklist

Kept current per the task-checklist rule (CLAUDE.md). Times are local ET.

- [x] A matching rule that creates a Company must name a source, its kind must
  hold the namespace's Identifier Contract, and the source must be one of that
  contract's issuing sources (fails closed, even while inactive) — unit,
  `TestAnIdentifierRule` (2026-09-24 18:44 ET)
- [x] A hand-matched record adds only identifiers its own source issues —
  PG16, `test_a_hand_matched_record_does_not_attach_its_lei_within_the_batch`;
  fails without the fix (2026-09-24 18:25 ET)
- [x] Gap 3, part: the candidate rule is data in the Company policy, checked
  and not active — unit, `TestTheCompanyPolicy` (2026-09-24 18:44 ET)
- [ ] Gap 3, rest: the SEC contract names the rule — waits on tickets 05, 06
- [x] Three-axis `/code-review`; fixes: fail closed without a contract, new
  rule version, issuers looked up once per batch, names (2026-09-24 18:44 ET)
- [x] Full suite: 883 MDM unit, 570 architecture, Clean MDM PG16 green but
  the known `fastapi` baseline test (CLAUDE.md) (2026-09-24 18:44 ET)
- [ ] PR and CI green
- [ ] Noted, not fixed: `binding` looks up a namespace's contract in any kind,
  `activation` in the rule's own kind. They agree while only Company declares
  `cik` and `lei`; Person or Fund declaring one would need a single lookup.
