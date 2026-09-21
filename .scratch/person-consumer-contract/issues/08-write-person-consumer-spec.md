# Write the Person consumer specification

Type: task
Status: resolved 2026-09-20

## Answer

Written: [`docs/specs/person/consumer.md`](../../../docs/specs/person/consumer.md)
(598 lines) — the Company consumer spec's contract headings, filled from
this map's sixteen resolved decision tickets, citing Clean MDM's tables
and design rows rather than restating them, with dependencies, five Open
items stated as Open, fourteen test obligations and twelve release gates.

Handover: [`.scratch/handover/2026-09-20-claude-to-codex-person-consumer.md`](../../handover/2026-09-20-claude-to-codex-person-consumer.md).

Written against Clean MDM's state as of `0c1449df` (#673), which accepted
three things this contract depends on: **Q13 / migration 028** durable
candidate assessments (which ticket 07's pre-merge replay requires),
**Q14** rules-as-data with Identifier Contract activation (which Person
Tier A uses), and **migration 029** per-family checkpoints. The one item
still open with Codex is the **Person amendment to Q11** — ≥ 99% at a
one-sided 97.5% bound plus the identifier-namespace veto — restated in
the handover with the measurement behind both numbers.

Stated plainly in the spec, not buried: **Tier B does not activate at
release**, the entity arm of rule C-J is gated on re-measurement, and
holdings publish nothing until a Security identity exists and the
`owner_index` defect is fixed.

Blocked by: none. All six decision tickets are resolved: 02, 03, 04, 05,
06, 07 — plus 20, which supersedes ticket 02 §4's Tier B row.

## Question

Tickets 09 and 10 are **not** blockers for writing the spec; they are
release-gate inputs the spec names as dependencies.

Nothing to decide. Write `docs/specs/person/consumer.md` to the same
contract headings as the Company consumer spec, from this map's resolved
tickets; cite Clean MDM's tables and design rows, never restate them; name
dependencies and release gates; then a handover note to Codex under
`.scratch/handover/`.

Carry these forward explicitly (they cross several tickets):

- The **operator principle** — every source resolves every entity it
  carries through MDM; no local or derived identity key anywhere
  (ticket 20) — with its named consequence for gold's owner key.
- The **pre-merge candidate table is a requirement**, not a proposal,
  because replay re-enters there (ticket 07).
- Tier B does **not** activate at release: 8-K is Tier C until ticket 21
  clears 97.5%; DEF 14A waits on ticket 10 (tickets 20, 07).
- Open items to state as Open, not to decide: whether legacy steward
  decisions are still reachable (ticket 06); the graph publication side —
  how an interval list and the `IS_INSIDER` view materialize into
  `MDM_GRAPH_EDGES`, and what the Agent Query Surface may read.
