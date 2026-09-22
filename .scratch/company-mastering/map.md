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
  — **a mapping version is a column on the assertion, not part of its hashed
  body; a re-read adds a row instead of rewriting one; two rows are kept, the
  current and one backup, plus any a live decision still cites; registration
  re-reads nothing by itself; and the identity parts of a contract may never
  change within one `source_code`.** Migration 031 designed, not written.

## Not yet specified

- **Which cohort the Proving Run uses.** The 1,000-row research cohort and its
  308 adjudicated links exist, but they are not independent truth. Company Q3
  wants a frozen CIK manifest. Sharpens once the policy executes.
- **How a deferred match is retried** when evidence or rules change (Q6): what
  triggers the retry, and what bounds the re-projection.
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
