# Approve a source or one rule by saying so, on its test evidence

Type: task
Status: in progress (Claude, branch `claude/rules-14-easy-approval`, 2026-09-29 18:15 ET)
Blocked by: nothing
Blocks: the GLEIF and SEC fixes of company mastering ticket 18 taking effect;
ticket 20's approval

## Operator rulings (2026-09-29)

- "The command is awkward … This is nuts": approving must not need a
  database address, a password or a 64-character digest.
- "I need to be able to approve a complete source or individual rules".
- "Make this part of a skill": the rules skill.
- "Rules must be self explanatory": the operator approves what they read,
  in plain words.
- "Rules can't be approved without test evidence, it can be overruled but
  test evidence must exist".
- Agreed (Claude's recommendation): the operator approves by saying so in the
  skill; Claude records it under the operator's name, with their exact words
  and the time; Claude never records an approval without those words. This
  replaces "Never approve … Never run it yourself" in `skills/rules/SKILL.md`
  and the separate approver login.

## Found (2026-09-29 18:15 ET)

- The local Rules Database (`rules` on `edgartools-clean-mdm-pg16`) is
  initialized (roles `rules_owner`, `rules_agent`, `rules_approver`) but
  holds **no version**: nothing has ever been saved, proved, approved or
  activated through it. No login is a member of `rules_approver`.
- No `RULES_DATABASE_URL`, `RULES_MDM_ACTIVATION_DATABASE_URL`,
  `CHANGE_LEDGER_DATABASE_URL` or `MDM_DATABASE_URL` is set in Claude's
  shell, and the `rules_agent` credential is not in any file found. It must
  come from the operator's environment (never through `!`, never printed).
- Today's rules (`001_rule_version.sql`): `proven` requires a passing proof
  (`proof.passed = true`); `approved_by` must be the session user and a member
  of `rules_approver`; `migrate()` refuses an agent holding approval rights.
- Single merge rules are already approved by stamps in the files
  (`approved_by`, `approved_at`, `reason` on an activation's proof in
  `merge/policy.yaml`; `check_policy` enforces them; ticket 15 filled them
  on the operator's word). Approving one rule reuses them: no second store.
- Plain words cannot live in YAML comments (`files.py` drops them on export)
  or as new fields in rule bodies (that moves every approved digest).

## Design

1. **First, the path end to end, by hand** (advisor, 2026-09-29): take the
   merged GLEIF source through `rules save`, `record-proof`, `activate`, as
   `rules_agent` (never the superuser), and write down every stop: what a
   source's proof needs (a passing acquisition validation, a pinned batch
   hash), whether MDM registration requires an approved Rules version
   (#738's registration authority), which logins activation needs. Until
   then the ticket 18 fixes are merged but **not in effect**.
2. **Migration 003** (tested on a populated `rule_version`, including rows
   approved the old way):
   - a proof may be recorded failing; it must still pin the version's digest
     and batch;
   - approval needs a recorded proof, enforced in SQL (missing evidence is
     never overruled); a failing proof is approved only with an overrule
     reason, and activation then requires that approval;
   - the approval record: the approver's name, their exact words, the time,
     the evidence it rests on, the overrule reason if any, and the session
     user that recorded it;
   - `rules_agent` may record an approval; `migrate()`'s guard changes on
     purpose, citing the ruling.
   - Edge: activation re-validates a source's acquisition proof, so an
     overruled source that cannot be read still does not activate.
3. **Commands** (no digest typed): `rules pending` lists what awaits approval
   with a plain-words change summary (a diff against the active version, and
   the note saved with the version) and its evidence counts; `rules approve
   --source <name>` or `--merge <name> [--rule <rule_id>]` with `--by`,
   `--words` and `--overrule <reason>` approves the latest version with
   evidence. `--rule` fills that rule's file stamps and approves the merge
   version they produce, from one sentence.
4. **Skill:** `skills/rules/SKILL.md` "Approve" mode: show plain words and
   evidence, take the operator's words, record; refuse without evidence;
   ask for a reason to overrule. Replace "Never approve" with the ruling.
   Memory updated the same way.
5. **First use:** the GLEIF and SEC source versions of ticket 18. Ticket 20's
   labelling stays out of this ticket.

## Checklist

- [ ] Step 1 by hand; record each stop here.
- [ ] `/gof-refactor-reviewer` before code.
- [ ] Migration 003 and its PG16 tests (populated table).
- [ ] `rules pending`, `rules approve` without a digest, `--rule`.
- [ ] The skill's Approve mode; SKILL.md and memory changed on purpose.
- [ ] Three-axis `/code-review`, PR, CI; merge on the operator's word.
