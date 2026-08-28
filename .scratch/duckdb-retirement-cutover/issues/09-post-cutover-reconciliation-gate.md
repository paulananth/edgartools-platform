# 09 — Post-Cutover Reconciliation and Human GO/NO-GO Gate

**What to build:** Run [Ticket 06](06-build-table-specific-reconciliation-tooling.md)'s
tooling against the post-cutover state produced by
[Ticket 08](08-atomic-write-path-cutover.md), producing the fail-closed
assertion DuckDB Retirement's Ticket 07 (wayfinder decision) requires, and
route the result to a required human approval before the cutover is
considered final.

Kept as its **own** ticket rather than folded into Ticket 08's deploy step
deliberately: Ticket 07's standard is "automated fail-closed assertion
gating a required human approval" — putting the approval inside the same
ticket as the deploy invites self-certification (the agent that ran the
deploy also signing off on it). A separate ticket makes the human-approval
step a real handoff, matching this repo's `Gate Attestation` /
`Direct-Evidence GO` pattern (`CONTEXT.md`) rather than a rubber-stamp
embedded in the same change.

If reconciliation fails for any table, this ticket's job is to surface that
failure clearly (which table, which check) — not to attempt an automatic
rollback itself. Rollback mechanics, if reconciliation fails, follow Ticket
01's rollback answer (all-or-nothing across the write path + reader
cutovers), executed as a separate, explicit operator action.

**Blocked by:** [Ticket 08](08-atomic-write-path-cutover.md)

**Status:** blocked

- [ ] Ticket 06's reconciliation tooling runs against the real post-cutover
      state (not a dry run) and produces a PASS/FAIL per table
- [ ] `sec_thirteenf_holding`'s large-scale case passes (or a documented,
      understood failure blocks GO)
- [ ] A named human operator records an explicit GO/NO-GO decision, bound to
      the specific deploy/reconciliation evidence — not an inferred or
      default approval
- [ ] If NO-GO: the specific failing table(s) and check(s) are documented
      clearly enough for the rollback decision to be made without
      re-deriving the failure from scratch
