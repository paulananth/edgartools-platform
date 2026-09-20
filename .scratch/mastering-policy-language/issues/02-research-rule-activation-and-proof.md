# Research: how a declared rule becomes active, and where its proof lives

Type: research
Status: resolved
Blocked by: none

## Question

Q5 of the charting grill. A rule in the policy document is either
**declared** (fires, result goes to a Steward) or **active** (fires, the
Merge Stage binds or consolidates alone). Activation needs a proof —
Clean MDM's accepted Q11 ("≥ 99.9% precision before any automatic rule";
Person amended to 99% by the operator) and Q16 (all automatic rules
disabled until then). Where should the proof live, and what is the
simplest activation model an operator can maintain?

Options on the table:

- (a) the proof travels **inside the document next to the rule** (sample
  size, correct count, lower confidence bound, cohort hash, who/when), and
  the Merge Stage accepts an automatic rule only when that block meets the
  kind's declared bar;
- (b) the proof lives **outside** in a calibration record; the document
  only says `status: active`, set by a Steward;
- (c) both, linked by a hash the Merge Stage checks.

Establish, from primary sources:

1. **What Clean MDM already provides or constrains.** How `automatic_rules`
   is refused today (`clean/merge.py`), what the `policy` digest pins, what
   `merge-stage.md` says about "versioned policy evidence", "calibration",
   "numeric calibration and versioned policy evidence are missing", and
   how Steward overrides are recorded (governed assertions with reviewer,
   reason, evidence, scope, expiry). Is there any existing calibration or
   evidence table in `mdm_v2` or the Change Ledger that (b)/(c) could
   reuse? Cite `path:line`.
2. **What a proof must contain to be re-checkable**: research 18
   (`.scratch/person-consumer-contract/research/18-summary.json`,
   `18-sample.jsonl`) and research 16 are the two proofs produced so far.
   What fields did they need (sample, labels, script hash, data hashes,
   Wilson bound, cohort)? Would a proof block in the document be small
   (numbers + hashes) or large (the sample itself)?
3. **How established tools activate a rule.** From primary docs only:
   Informatica MDM (match rule set "active"/inactive, rule-set
   promotion), Reltio (match rule "auto-merge" vs "suspect"/"potential
   match" thresholds — where the threshold is set and who changes it),
   Tamr (model publish / "verified" clusters), Splink (no activation
   concept — thresholds in the settings object; document that), Senzing
   (config versions, `CONFIG_ID` pinned per run). What is the unit of
   activation, who does it, and is the evidence stored with the config?
4. **Failure modes to weigh**: a rule active without proof; a proof for an
   older rule version; a bar change (99.9 → 99) that should deactivate
   rules; replay of an old batch under a rule that was later deactivated;
   an operator editing the document by hand.

Then answer plainly: the simplest model that keeps one digest reproducing
one result, is hard to get wrong by hand, and stays maintainable when the
platform has 8 kinds and 20 sources — one paragraph the operator can read
alone, then the detail. Recommend a concrete shape (the fields of a rule's
activation block, or the record it points to) and the exact check the
Merge Stage performs.

Write to
`.scratch/mastering-policy-language/research/02-rule-activation-and-proof.md`.

## Answer

**Option (a) with a hash pointer: the proof lives next to the rule, the sample
stays outside as files named by SHA-256, and no new table is needed**
([research/02](../research/02-rule-activation-and-proof.md)). Write the rule once
in its kind's document; activate it with a separate 923-byte entry naming
`(rule_id, rule_version, verdict)` and carrying n, correct, the lower bound, the
adversarial result, the cohort and file hashes, and approver/when/why (§2). The
bar is declared per `(kind, family)` in the kind document, so Person's 99% and
Company's 99.9% are each one line. The Merge Stage check is a pure predicate that
recomputes the bound and compares it to the bar, replacing the truthiness refusal
at `merge.py:183-184` and `store.py:155-156` with `qualified(policy)`; three of
the four named failure modes fall out of the digest for free, and the fourth
(a fabricated proof) is answered by attribution plus a CI re-scoring job, not by
code (§6). **Per-verdict activation is the key finding** — it is what lets rule
C-J's `person` arm go live while its `entity` arm stays review-only, exactly as
Person ticket 03's gates 1–2 require. Clean MDM already embeds authority evidence
this way (`store.py:205`, re-verified at `023:155-158`) and already makes policy
registration owner-only, so no new role or table is introduced; none exists to
reuse anyway (§3). Of five tools surveyed only Tamr stores a measurement with
activation, and only per project-publish (§5). Open for Codex: Q11 says one-sided
95% but research 18 measured at one-sided 97.5% — n ≥ 268 vs n ≥ 381 at a 99% bar
(§4, §7).
