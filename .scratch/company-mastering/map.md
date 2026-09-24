# Company mastering: run it from a versioned policy

Label: `wayfinder:map`

## Destination

A Company is bound from SEC and GLEIF evidence by a **versioned policy the
engine executes**, not by decisions written into a fixture. Proven locally on
a pinned cohort against real PostgreSQL 16, reported as what the rules *would*
decide. **No rule is activated without the operator's explicit approval of its
exact digest.** This map carries execution, not only decisions (see Notes).

## Notes

- **Handed over by Codex**, 2026-09-22, after Clean MDM ticket 12 merged
  (#693): [Company mastering handover](../handover/2026-09-22-company-mastering-to-claude.md)
  and its [Source Contract response](../handover/2026-09-22-codex-source-contract-response.md).
  Its instruction: settle the shared Dataset Contract and the Mastering Policy
  execution boundary **first**, then implement predicates.
- **This map carries execution.** Wayfinder plans by default; here the later
  tickets build, because the decisions and the code share one seam and the
  operator asked for the work, not a hand-off.
- **What already exists** (do not rebuild): the shared Merge Stage
  (`edgar_warehouse/mdm/clean/merge.py`, `identity.py`, `survivorship.py`,
  `assessment.py`, `relationships.py`, `store.py`), native GLEIF evidence and
  whole-publication accounting (`gleif_source.py`, `native_consumption.py`,
  `source_publications.py`, migrations 028-030), and the `lei` format with ISO
  check digits.
- **The blocking fact:** a dataset body is immutable per `source_code`
  (`store.py:217-224`) and assertions are keyed by it
  (`023_clean_mdm.sql:50`). A mapping change today means a new `source_code`
  and re-binding every record. Codex calls that an unacceptable lifecycle.
- **The runtime refuses every automatic rule** (`store.py:162`,
  `merge.py:303`). Nothing binds automatically until predicates are
  implemented and tested. That refusal is the safety net; it comes out only
  with its replacement in place.
- **Accepted policy** (do not reopen): [Company Q1-Q14](../../docs/specs/clean-mdm/company-policy.md),
  the [completion gate](../../docs/specs/clean-mdm/company-completion.md), and
  the proposed [policy language](../../docs/specs/mdm/policy-language.md).
  Q14 lets an identifier-only binding activate through a verified Identifier
  Contract; fuzzy binding and published-ID consolidation keep their own
  statistical gates.
- **Verification bar** (Codex's, adopted): `uv`, real PostgreSQL 16, restricted
  runtime roles, fixtures that fail rather than skip. Prove reordered and
  duplicate input, stale assessment rejection, lost acknowledgements, no false
  completion, retained field conflicts, incorrect-merge reversal and stable
  surviving IDs. A fixture's explicit decision is never evidence of automatic
  matching.
- **Standing rules:** never commit to `main`; one worktree per topic; Codex's
  Clean MDM files are shared now, not read-only, but any change to them is
  minimal and reviewed; zero SEC requests; nothing is deployed until it is
  written and tested locally.
- Skills: `/grilling` (one question at a time, with a recommendation),
  `/domain-modeling`, `/tdd` at the policy and transaction seams,
  `/code-review` on three axes, `/gof-refactor-reviewer` before touching
  production code.

## Decisions so far

- [Decide how a Dataset Contract version changes without re-binding every record](issues/01-decide-dataset-contract-versioning.md)
  — **a re-read adds a row instead of rewriting one; registration re-reads
  nothing by itself; and the identity parts of a contract may never change
  within one `source_code`.** Amended after the challenge pass: **the mapping
  version is part of the assertion's identity**, so it goes in the hashed body
  and is lifted into a `bigint` column, and **the revision guard's key widens
  to `(revision, mapping_version)`** — without both, a re-read either crashes
  the merge or is silently dropped — and **assertions are never pruned**, since
  the store is append-only throughout and the prune bounded something the
  explicit-re-read rule already bounds. Migration 031 designed, not written.

- [Challenge tickets 01 and 02 against the code](research/01-02-challenge.md)
  — eight of the twelve decisions sound, four not: the two amended above, the
  retention rule, and the suspension line in ticket 02. Migration 031 is free
  and the uniqueness rule it targets is unchanged; the bar arithmetic
  reproduces the spec exactly.

- [Settle the Mastering Policy execution boundary](issues/02-settle-the-policy-execution-boundary.md)
  — **one home per kind (`kinds.<kind>`, fields included); classification is
  governed by the policy but the decided kind stays stamped on the evidence;
  a field records its kind's own digest, not the whole body's; each kind keeps
  its own accepted bar (Company 99.9% at 95%, Person 99% at 97.5%); suspension
  lives in its own table and never edits the policy; and coherent field groups
  are filled whole or left unknown.** Amended after the challenge pass: the
  suspension row is keyed by `(policy_digest, kind, family, rule_id,
  rule_version)`, not a "rule digest", and **its line is scoped to §9.3
  deterministic rules per namespace** — applied to every automatic verdict it
  made a rule accepted at 99.9% suspend itself about nine times in ten.

## Added tickets

- [Qualify the first SEC-to-GLEIF Company binding rule](issues/08-qualify-sec-to-gleif-fuzzy-binding.md)
  (added 2026-09-23, blocked by 04; now blocks 05). Tickets 03 and 04 only
  make a Company recognisable within one source: SEC and GLEIF share no
  identifier the adapters map (SEC's own `lei` key is unmapped and was null
  for all four Companies checked), so the first link between them needs Q4's qualified fuzzy
  matching, which no ticket built. Without it the Proving Run would report
  every Company as "no GLEIF match" and the milestone would look complete.

## Not yet specified

- **Which cohort the Proving Run uses.** The 1,000-row research cohort and its
  308 adjudicated links exist, but they are not independent truth. Company Q3
  wants a frozen CIK manifest. Sharpens once the policy executes.
- **Whether a measured rule needs a runtime kill switch, and at what line.**
  Ticket 02's amendment scopes the suspension counter to §9.3 deterministic
  rules, where the only measured line lives. A rule accepted at 99.9% is
  therefore stopped by nothing until the next proving run. A line for that
  family has to be derived against its own bar, on rules that exist; sharpens
  once a Proving Run has produced some.

- **How a deferred match is retried** when evidence or rules change (Q6): what
  triggers the retry, and what bounds the re-projection.

- **How the classification rule reaches the code that uses it** (ticket 02
  answered where it sits, which was half the question).
- **Consolidation of two published Company IDs** (Q10, Q11): its own
  statistical gate, after binding works.
- **Relationship and lifecycle work** (parent links, duplicate LEI successors,
  reporting exceptions as evidence): named in the handover's item 5, but it
  waits until a Company binds at all.

## Out of scope

- Person, Adviser, Fund, Security and every other entity kind: the Company
  completion gate forbids starting them first.
- Hosted qualification, Snowflake, export and graph cutover: separate consumer
  and release gates.
- The Source Contract engine itself: Codex's, and the contract reads a
  fixed-shape artifact only.
- Reopening Company Q1-Q14 or the accepted GLEIF field semantics.
