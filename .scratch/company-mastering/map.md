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

- **Lean, clean, KISS** (operator, 2026-09-26 13:03 ET): a simple MDM, with
  sources fully decoupled and new MDM fields easy to add. When a layer causes
  a problem, remove the layer; do not tune it or add work around it. First
  applied in [Keep each Company in one place](issues/17-keep-each-company-in-one-place.md).

## Decisions so far

- **Source priority is set per entity kind** (operator, 2026-09-24 09:45 ET): when sources
  disagree on a value, the kind's priority list decides. **Company: SEC first,
  GLEIF next.** Each kind (Person, Fund, ...) carries its own list in the
  Mastering Policy, changed by a new policy version, never in code. The policy
  already holds an ordered source list per field under `kinds.<kind>.fields`;
  the kind-level list is the default a field inherits unless it states its own.
- **The master takes fields from every source** (operator, 2026-09-24 09:59 ET): a field only
  one source has comes from that source; **priority decides only when the
  field exists in more than one**. Apple's master row therefore carries SEC's
  fields and GLEIF's fields together, SEC winning where both supply one.

- **The final authority is one dated Company table** (operator, 2026-09-24 08:28 ET):
  `mdm_v2.company`, one row per company version with CIK, LEI, other
  cross-references, name and every identifying field, and start and end
  dates, written only by the Merge Stage. No reader goes to two places for
  Company information. Built by
  [Write the versioned MDM Company table](issues/09-write-the-versioned-mdm-company-table.md).
- **The Stage is latest-only; bronze is the only history** (operator,
  2026-09-24 08:33 ET): one row per company per source, upserted; each row names its bronze
  object so an older version can be re-read from S3. Reverses ticket 01's
  "assertions are never pruned". Built by
  [Make the Stage latest-only](issues/10-make-the-stage-latest-only.md).

- **Confidence bands** (operator, 2026-09-24): for "is this a Company?" and
  for SEC-to-GLEIF matching, a decision whose tested probability is **95% or
  more** acts automatically; **50% to 95%** waits in the Stage, unreviewed,
  until the rule improves; **below 50%** goes to a Steward. The automatic bar
  falls from 99.9% to 95% for these two decisions only; publishing-ID
  consolidation keeps 99.9%. No Steward vets public data routinely: testing
  catches a weak rule. Recorded in
  [the Company policy](../../docs/specs/clean-mdm/company-policy.md).

- **One Company, one master record, whatever the sources** (operator,
  2026-09-24). Mastering exists because no source carries everything: SEC
  supplies the CIK, GLEIF supplies the LEI. Both source records are kept, side
  by side, in the Stage (`company_stage`); the mastered record
  (`company_master`) is **one** Company holding the CIK, the LEI and the
  selected fields from both. Two master records for one real Company is the
  failure this effort exists to prevent, not an intermediate state to
  consolidate later. Consequences: the SEC-to-GLEIF join (ticket 08) is on the
  critical path, not an enrichment; and "reuses its Company by LEI" (ticket 04)
  means an LEI already attached to that one Company, not a separate GLEIF
  Company.

- **A source record waits in the Stage until a matching rule links it**
  (operator, 2026-09-24). A GLEIF record the rules cannot yet tie to a Company
  stays in the Stage, tagged with its source (GLEIF), and creates no master
  record. It joins the one Company when a matching rule links it. The matching
  rule compares **the fields each kind declares for matching**, such as company
  name, ticker or CUSIP. **Matching and merging rules are written per entity
  kind, from that kind's sources**: a Company's rules compare what SEC and
  GLEIF carry, and a Person's or Fund's rules differ. This is the policy
  language's existing shape (`policy-language.md` §4.1: binding and
  survivorship sit at kind level). Open: which of those fields each source
  actually carries (ticket 08).

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

- [Ticket 09 handoff to Claude](issues/09-handover-to-claude.md) records PR #714,
  local proof, the unchanged policy fingerprint, and the next Company gates.

- [Correct an incorrect Company link](issues/13-correct-an-incorrect-company-link.md),
  [carry SEC countryCode into silver](issues/14-carry-sec-country-code-into-silver.md),
  and [approve the CIK binding rules](issues/15-approve-and-activate-cik-binding-rules.md)
  were opened at the operator's direction on 2026-09-25. They remain open;
  opening them activates no rule.

- [Write each SEC submissions document to bronze once](issues/16-write-sec-submissions-bronze-once.md)
  was opened at the operator's direction on 2026-09-25 21:10 ET. Today a
  same-day re-fetch overwrites the bronze object a Stage row names. It blocks
  ticket 10's slice 4. The operator chose the key: the content hash in the
  object's name (2026-09-25 21:17 ET).

- [Qualify the first SEC-to-GLEIF Company binding rule](issues/08-qualify-sec-to-gleif-fuzzy-binding.md)
  (added 2026-09-23; done 2026-09-26, its wrong-link reversal moved to
  ticket 13). Tickets 03 and 04 only
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
- **Rebuilding after a CIK contradiction** (Q9: "suspends the affected
  established link and rebuilds from remaining trusted evidence"). Ticket
  04 suspends new rule links to a Company in conflict review; nothing yet
  rebuilds it, and ticket 13 covers wrong name-rule links only.
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
