# Company matching and mastering: handover to Claude

The user asked whether Claude can own Company matching/merging/mastering.
Yes: take this work **after the Ticket 12 PR merges**, on a fresh `claude/<topic>`
branch in a dedicated worktree from updated `origin/main`. Do not commit on
`codex/company-native-gleif` or its PR branch. Codex owns Ticket 12 fixes until the
PR lands; this note does not authorize overlapping edits beforehand.

## Starting point

- Existing shared Merge Stage: `edgar_warehouse/mdm/clean/merge.py`, `identity.py`,
  `survivorship.py`, `assessment.py`, `relationships.py`, `store.py`.
- Ticket 12: native source verification and range consumption, existing root-run
  recovery, migration 030's registered retained-evidence dispositions, real PG16
  tests. See `docs/specs/clean-mdm/native-gleif.md` and
  `.scratch/clean-mdm/ticket12-acceptance.md`.
- SEC + GLEIF fields share one Company in a retained-source fixture using explicit
  test decisions. This is not proof of engine-selected matching.
- Golden Copy JSON ZIP historical qualification passed across all three archives.
  Their original bytes remain outside git in the existing local research cache;
  immutable hashes and counts are committed. No production rebuild is approved.
- Full raw verification currently repeats per invocation: integrate authenticated
  immutable parsed partitions before claiming production-scale consumption.

## Next Company work

Read `docs/specs/clean-mdm/company-policy.md`, `company-completion.md`,
`docs/specs/mdm/policy-language.md`, `docs/specs/source-contract/spec.md`, and
`2026-09-22-codex-source-contract-response.md` in this folder. Reconcile unresolved
schema/replay details before creating implementation tickets. Tell the user what
the next Company ticket does before starting it.

1. Settle stable Dataset Contract versioning: source subjects must not change just
   because mapping code changed. Keep exact mapping/policy versions replayable.
2. Implement shared policy classification, candidate predicates and field rules;
   reuse the existing Merge Stage and assessment transaction rather than build a
   second merger. Preserve coherent field groups, deterministic priority rules,
   null/clear/retract semantics and provenance.
3. Prove identifier-only Company binding through a verified Identifier Contract
   (accepted Q14). Compatible exact identifiers reuse the immutable master ID;
   authoritative conflicts defer. Fuzzy binding and published-ID consolidation
   keep their independent precision gates. The old research seed links are not
   independent truth labels.
4. Add the Rules Database/Proving Run handoff from Source Contract design.
   Production reads only active digest-pinned `mdm_v2` contracts. Rules Database
   versions, proofs and approvals never become another master-state transaction.
5. Exercise Company lifecycle corrections, typed parent links, duplicate LEI
   successor handling, replay/reversal, export and graph recovery. Keep Company
   ahead of Person and other entities.

Activation of any version able to bind or merge identities requires the user's
explicit Rule Activation Approval for that exact digest. Earlier general approval
of the architecture is not that activation. Local candidate-rule Proving Runs
should test automatic outcomes without publishing them or activating the rule.

## Verification bar

Use `uv`, real PostgreSQL 16, and the existing restricted runtime permissions.
The integration fixtures fail missing prerequisites, not skip. Run targeted TDD
at policy/transaction seams, then the complete checks. Prove reordered/duplicate
input, stale assessment rejection, lost acknowledgements, no false completion,
retained field conflicts, incorrect-merge reversal and stable surviving IDs.
Never substitute explicit fixture decisions for automatic matching acceptance.
