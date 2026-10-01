# Data Onboarding skill gaps found by the Person feed 1 onboarding

Type: task (skill and tooling)
Status: open, not started. Found by `05-onboard-person-feed-1.md`; each gap is
quoted with the skill's own words in
`.scratch/onboarding/sec.submissions.person/onboarding-log.md`, "SKILL-GAPs".

A cold agent could not finish a new feed by configuration alone. Every step
below needed code, a hand-made workaround, or an answer the skill should have
given.

## Checklist

- [ ] 1. Dry run needs code: build `rules check --source <s> --sample <n>`
  (rules-skill ticket 03)
- [ ] 2. Proving run needs code and Docker: build Preview (rules-skill ticket
  04), or ship `proving_run.py`'s shape as a command. It must stand in for a
  missing reader, and must not hang on store growth (05b)
- [ ] 3. Digest and input manifest need code: `rules save` prints the digest;
  a command writes the input manifest
- [ ] 4. The proof entry's shape is incomplete in the skill. Say:
  - the lower bound is cut to six places, never rounded (a rounded bound was
    refused);
  - what the adversarial set counts as a violation
- [ ] 5. Measuring the classification proof needs code: `rules measure`, plus
  the sample draw and the labelling-agent steps (Q7, Q12)
- [ ] 6. Writing and checking the rules files needs code: `files.source`
  round-trip as a command
- [ ] 7. Profile needs code: `rules profile` (rules-skill ticket 06)
- [ ] 8. Quality counts need code: part of `rules check`
- [ ] 9. Adding a kind broke pinned tests: fixed by #769 (05a). Add a line to
  the skill that a new kind leaves Company's pins alone
- [x] 10 (part). Fixed in #770: plain words for `token_match@1` and
  `name_shape@1`, "NOT (...)" for a negated condition, excluded words named,
  and a ceiling of 1 or more shown (2026-10-01 18:34 ET). Still open: Company's
  `max_count: 0` reads "at least  of the list", and the identifier words say
  "Company" for every kind.
- [ ] 10. Mapping Document bugs for a second kind:
  - a negated step is shown without "not";
  - "Company" is hard-coded in the matching rule text;
  - the arguments are shown raw
- [ ] 11. Catalog lineage is missing for a second kind read from another
  source's feed
- [ ] 12. The input manifest includes a non-feed file (the ticker catalog):
  say whether `batch_hash` covers only the feed's own files
- [ ] 13. Say up front which variables the whole walk needs. The Rules
  Database can be a local throwaway (operator, 2026-10-01: "no login needed")
- [ ] 14. APPROVE.md does not say how an identifier rule is approved. The
  approval goes on its Identifier Contract's `verification`, plus its
  `automatic_rules` entry, by hand; `rules approve --rule` records measured
  proofs only. Make it a command
- [ ] 15. Switch-on needs a Clean MDM database. Say which one, and what to do
  while the operator's local store holds the retired `mdm_v2` schema
- [ ] 16. Relationships come with MDM (operator, 2026-10-01). The skill must
  plan person–role–entity links in the same onboarding, including names that
  state a relationship ("a series of", "Trustee UAD", "dba", "ET AL")
