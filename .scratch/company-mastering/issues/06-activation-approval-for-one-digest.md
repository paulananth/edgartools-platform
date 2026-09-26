# Ask for the Rule Activation Approval of one exact digest

Type: grilling
Status: open
Blocked by: 05 (Phase 1 done 2026-09-26; ready to ask)

## Question

The operator approves one exact policy digest, or does not. Earlier approval of
the architecture is not this approval.

Bring: the digest, what the rule may do (bind by identifier only), what it may
not (fuzzy binding, consolidation), the Proving Run's numbers, and the
reversal path if it is wrong. Record the answer as the approval or refusal of
that digest, and register it through the governed path, never as a second
master-state transaction.

## The brief, prepared (Claude, 2026-09-26 13:00 ET)

Nothing here is the operator's answer; it is what they are asked.

- **The digest:** `36637a09b23cd2672ab75df3a47b5d26012d3ba2ab7e4237a318c0e48715bbba`,
  the body in `research/05-candidate-policy.json`, policy version
  `company-2026-09-26.cik-matching-rule`. It is today's approved Company
  policy (`983352e8…4049`) plus one rule, one Identifier Contract and one
  switch.
- **What it may do:** give each SEC record the Company rule accepts exactly
  one Company, by its CIK. It joins the Company that already holds that CIK,
  or creates one when none does.
- **What it may not do:**
  - match by name, which stays declared and off;
  - consolidate two published Companies;
  - give a Company an LEI;
  - act on a record the Company rule held back.
- **The Proving Run's numbers** (ticket 05, Phase 1):
  - 6,414 of 6,414 Companies each became one Company by their CIK, Apple,
    Microsoft, Shell and ASML among them;
  - 0 controls became a Company;
  - no CIK sits on two Companies;
  - a second pass changed nothing.
- **The reversal path if it is wrong: none yet.** A Company the rule
  creates cannot be undone today. The Merge Stage refuses to move an
  established binding without a correction contract, and none is built.
  Ticket 13 builds one, but only for name-rule links. The risk comes from
  the Company rule: at its measured lower bound, up to about 57 of 6,414
  records could be mislabelled; the point estimate is 0.
- **After approval:** the three approval fields carry the operator's name,
  time and reason, which changes the digest. Show that final digest for a
  last review before any shared registration (as ticket 12 did).

### Before asking (open, 2026-09-26 13:30 ET)

- **Production must build exactly this body.** The live Company policy is
  built from `policies/company.json` (`load_kinds`) and `company_source.py`
  (`POLICY`, version `sec-company-local-v2`, with `APPROVED_ACTIVATION`). The
  Proving Run's body comes from its harness (`05_proving_run.py`,
  `candidate()`). Before the ask:
  - draft the production edit;
  - confirm that production then builds `36637a09…bbba` without the approval
    fields;
  - if it cannot express the body (the rule's place in `rules`, the
    `identifiers` block, the version name), say so in this ticket.
- **Settle the verification block before the ask.** It holds only the
  corpus hash today. The spec's `verification` names "counts, bound, corpus
  hash, who/when". Adding the Proving Run's counts changes the digest, so
  decide first.
- **Tolerance:** the line used is the spec's `sec.cik` row, which the spec
  wrote for a Person. With `kind_equal@1`, its name-mismatch alarm may never
  fire for a Company.
