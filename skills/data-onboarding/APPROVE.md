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
2. **Explain it.** Tell the operator, in plain words and business terms:
   what it is (its name, never a digest), what it changes, and what the test
   run showed.
3. **Record the approval.** A version whose test run passed is approved
   under the operator's standing approval (2026-10-15: "Approved the rules
   always"), with that test run as its evidence: record those words, no
   question. Ask, and wait for their words, only for a failing run (step 4)
   or a new kind of decision; switching on (below) always waits for them:
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
`activation: deterministic`) has no measured proof: its evidence is a
Proving Run where each identifier landed on one entity.

1. Say in plain words what it joins and what the Proving Run showed: how
   many records joined, waited or were created, and that no identifier sits
   on two entities.
2. Wait for their words, then:
   ```bash
   edgar-warehouse rules approve --merge platform --rule <rule_id> \
     --proof <the Proving Run report> --reason "<one line of its counts>" \
     --by "<their name>" --words "<their exact words>" --at <when they said it, UTC>
   ```
   It adds the rule to `automatic_rules` in `rules/merge/policy.yaml`, under
   a comment with their words, their time in ET, the report's name and its sha256. When the
   identifier's Identifier Contract has no `verification` yet, it stamps
   one from the report (`corpus_sha256`, `approved_by`, `approved_at`,
   `reason`). A contract already verified keeps its stamp. Both files keep
   their comments.

   **Refused:** no report file, no reason, a rule that does not join on an
   identifier (use the measured-proof steps above), or one already on. The
   files are left as they were.
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
proving run's). A database that still holds the retired schema `mdm_v2` is not
it: `mdm migrate` refuses it ("Recreate the database and migrate it from
empty"), so create a fresh database and migrate that; the old one is the
operator's to drop.

- **Worked:** `rules status --source <name>` shows the version `active`.
- **Refused:** there is no approval, or no proof. Go back one step.

Switching on the pipes and switching on live data are apart (operator,
2026-10-19). A source version proven on its test run over captured files and
approved activates: Bookkeeping then runs its targets over captured files.
Live acquisition (a run with a feed, the capture worker) also needs an
acquisition proof: the receipts of a real acquisition run of that source, not
a test fixture or a copy made by hand. A recorded proof never changes, so to
switch live data on later, save the same rules as a new version, record a
proof holding the test run and the acquisition evidence, then approve and
activate that version.

Then tell the operator it is in effect. Running a feed is the Bookkeeping
skill's **run** mode, not this one.
