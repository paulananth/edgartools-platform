# Approve, then switch on

Shared by Data Onboarding and Refining Rules. Nobody types a digest, a login
or an address: the operator (or a steward, for their own Mapping Document
change) approves by saying so, and you record their words.

## Before you ask

The version is saved and has a test run: `rules save`, then `rules
record-proof` (the skill's **test** mode). A version with no test run cannot
be approved. The operator may overrule a *failing* run, never a *missing*
one (operator, 2026-09-29).

## Approve a source version or a merge version

1. **List what waits.**
   ```bash
   edgar-warehouse rules pending
   ```
   Needs `RULES_DATABASE_URL` (the `rules_agent` login). For each version
   that has a test run and no approval, it prints:
   - whether the run passed;
   - its evidence (counts and up to 10 examples);
   - its note;
   - `changes`: what it changes from the active version, value by value;
   - its `evidence_hash`.

   **Worked:** the version you saved is listed. **Not listed:** it has no
   test run. Go back to the skill's **test** mode.
2. **Explain before you ask.** Tell the operator, in plain words and
   business terms: what it is (its name, never a digest), what it changes,
   and what the test run showed. Then ask one question: "Do you approve
   <name>?" Give your recommendation.
3. **Wait for their words.** Record only an approval they gave, for that
   version:
   ```bash
   edgar-warehouse rules approve --source <name> \
     --version <v> --evidence <evidence_hash> \
     --by "<their name>" --words "<their exact words>"
   ```
   Use `--merge <name>` in place of `--source` for merge rules. You pass the
   version and `evidence_hash` that `rules pending` showed; the operator
   never types them.

   **Worked:** it prints the approved row. The database keeps the name, the
   words, the time, a hash of the evidence and your login.

   **Refused because the test run changed since you showed it:** show the
   new run and ask again.
4. **A failing run.** Approve it only when they overrule it, giving their
   reason. Ask for the reason and add `--overrule "<their reason>"`. If you
   think the overrule is wrong, recommend against it once and say why.

   A source whose files could not be read (its acquisition checks failed)
   is never overruled. The approval is refused.

## Switch one declared matching rule on

A matching rule declared in `rules/merge/kinds/<kind>.yaml`, with its proof
in `rules/merge/pending-proofs.yaml`:

1. Say in plain words what it joins and what its proof measured: the
   sample, how many were right, and the adversarial pairs.
2. Wait for their words, then:
   ```bash
   edgar-warehouse rules approve --merge platform \
     --rule <rule_id> --by "<their name>" --words "<their exact words>"
   ```
   It adds the rule to `rules/merge/policy.yaml` with its proof and the
   approval, keeping the file's comments. It refuses a rule with no proof,
   or one short of its kind's bar. A single rule is not overruled here: log
   it for a ticket.
3. The merge rules that carry it are a new merge version. Save it, record
   its test run, and record the same words on it when `rules pending` shows
   it changes only that rule.

## Switch on an identifier matching rule

A matching rule that joins on an issued identifier (`identifier_match@1`,
`activation: deterministic`) has no measured proof for `rules approve
--rule`: its evidence is a Proving Run where each identifier landed on one
entity. No command records it yet, so after the operator's words, by hand:

1. In the kind's file, the identifier's Identifier Contract gets
   `verification`: `corpus_sha256` (the Proving Run's report), `approved_by`,
   `approved_at` (the time of their words) and a one-line `reason` with its
   counts, as a switched-on Identifier Contract in the kind files shows.
2. `rules/merge/policy.yaml` gets the rule in `automatic_rules`: `kind`,
   `family: binding`, `rule_id`, `rule_version`, `verdict: bind`,
   `activation: deterministic`, under a comment with the operator's words
   and the ET time.
3. The policy is then a new merge version: its pinned digests move, as for
   any merge-rule change.

## Switch on (activate)

```bash
edgar-warehouse rules activate --source <name> --version <v>
```

Use `--merge <name>` for merge rules. It needs `RULES_DATABASE_URL` and
`RULES_MDM_ACTIVATION_DATABASE_URL` (the MDM governance login). It registers
the approved version in MDM and records the handoff receipt.

**Which MDM database.** The one the MDM runs read and write: the governance
login opens it, and its schema is `mdm`, created and upgraded by
`edgar-warehouse mdm migrate`. Locally that is a disposable PostgreSQL 16 (the
proving run's). A database that holds only the retired schema `mdm_v2` is not
it: nothing reads `mdm_v2` any more, so migrate a fresh database rather than
registering there, and leave the old schema to the operator.

- **Worked:** `rules status --source <name>` shows the version `active`.
- **Refused:** there is no approval, or no proof. Go back one step.

A source version is activated only with an acquisition proof: the receipts
of a real acquisition run of that source, not a test fixture or a copy made
by hand. A merge version and a source's mapping can be approved and proved
on captured files first; switching the source itself on waits for that run.

Then tell the operator it is in effect. Running a feed is the Bookkeeping
skill's **run** mode, not this one.
