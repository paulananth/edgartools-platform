# Write the Person consumer specification

Type: task
Status: resolved 2026-09-20

## Answer

Written: [`docs/specs/person/consumer.md`](../../../docs/specs/person/consumer.md)
(608 lines, 20 sections) — the Company consumer spec's contract headings, filled from
this map's sixteen resolved decision tickets, citing Clean MDM's tables
and design rows rather than restating them, with dependencies, five Open
items stated as Open, fourteen test obligations and twelve release gates.

**Documentation review, 2026-09-20** (the foundation spec's gate-4 pattern):
every `path:line` citation and every headline figure re-verified against the
repository and the research files. Four defects found and fixed — all
overstatements of what was measured, none in the decisions themselves:

1. `company-completion.md:71` moved to `:80` in Codex's #673; the citation
   pointed at an unrelated sentence.
2. Gold's owner key was described as "a hash of `'cik:' || …`". It is
   `party_nk`, a concatenated natural key, surrogate-hashed separately into
   `party_key` (`ownership_holdings.sql:63-68`, `:80`).
3. **The name-only source figures were wrong in the spec's favour.** It
   claimed 8-K names are 97.7% plausible (research 01's looser measure) and
   that 58.7% of DEF 14A names are role text. Research 17 F1 measures 8-K at
   **53.2%** person-shaped (4,193 of 7,878) and DEF 14A at **41.3%** (6,091
   of 14,755), where the DEF 14A loss is ticket 10's 47% role-text leak
   *plus* single-token and honorific rows. The spec now uses the stricter
   figures and says why the two studies differ.
4. `72,981 over 21,727 distinct CIKs` conflated research 17 (14,566 distinct
   owner CIKs) with the Mastering Policy map's research 07 (104,970 rows,
   21,727 CIKs); the "no one-CIK-two-people" result belongs to the latter and
   is now attributed to it.

Also corrected: the unit test row conflated research 18's primary corpus
(841/841 person, 353/353 entity, 26 deferred from `18-sample.jsonl`) with the
pooled entity figure (507/507, primary + extension sample).

Wilson arithmetic re-derived independently: for a perfect record the lower
bound is `n/(n+z²)`, giving 0.98801 at 95% and 0.98307 at 97.5% for n = 223,
0.99033 / 0.98632 for n = 277, and 0.99295 / 0.99002 for n = 381 — so n ≥ 381
is indeed the threshold for 99% at one-sided 97.5%. All other cited figures
(841/841 LCB 0.9955, 507/507 LCB 0.9925, ~1.1% deferred, `OwnerID` 99.7%,
5,322/5,322 stable, 110/110 name-exact, 398 of 10,042 cross-issuer names,
3 of 3,981 shared CIKs, 27-to-1 ADV residual, 11 of 166 homonym pairs)
reproduce against their sources.

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
