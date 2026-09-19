# Write and evidence the pre-merge staging proposal

Type: task
Status: resolved
Blocked by: none

## Question

Does Clean MDM's rebuild already follow the match/diff-changed/multi-source-
merge/insert-or-update pattern legacy MDM implements in
`edgar_warehouse/mdm/resolvers/base.py`? If a distinct "pre-merge stage
after de-duplication" doesn't already exist, write an evidenced proposal for
one — sized as a recommendation for Clean MDM's owners (Codex/Grok) to
evaluate, not an implementation, per the ownership boundary this map's Notes
explain.

## Answer

### Does Clean MDM follow the pattern? Yes — more rigorously — with one
### piece deliberately switched off

Read directly from `origin/codex/clean-mdm-integration`
(`edgar_warehouse/mdm/clean/merge.py`, `edgar_warehouse/mdm/clean/survivorship.py`)
and `docs/specs/clean-mdm/merge-stage.md`:

| Legacy pattern (operator's description) | Clean MDM equivalent |
| --- | --- |
| check if entity already exists | `identity.replay()` resolves current bindings from the accepted decision graph (`merge.py:207`) |
| check if attributes changed | `survivorship.select_fields()` (`merge.py:249-...`), called inside the same transaction |
| multi-source merge before insert | Field authority order: steward override → versioned source rank → effective time → publication time → stable key (`merge-stage.md:122-130`) — stricter than legacy's single `mdm_source_priority` table |
| insert if not found / update if found | `identities` (new) vs. `decisions` (bind/merge against existing) in the same `apply()` call (`merge.py:117-124`) |

One thing is **not** equivalent: legacy resolvers run automatic fuzzy/exact
matching every pass (`MatchPipeline`/`MDMRuleEngine`, gated only by
`_skip_if_unchanged`'s content-hash short-circuit). Clean MDM's automatic
matching is **explicitly disabled** in this release —
`merge.py:5`: "Neither auto binding nor automatic consolidation is enabled
in this release." A match only happens today via an already-accepted
decision or an explicit steward review, gated behind Q11's requirement for
a demonstrated 99.9% precision bound before any automatic rule activates
(`merge-stage.md:53-64`). This is a deliberate, already-accepted policy
choice (Q16), not a gap.

### The atomic-transaction design, and why "add a pre-merge stage" is not a
### small addition

`MergeStage.apply()` (`merge.py:108-...`) does identity resolution, conflict
detection (`kind_conflict`/`authoritative_identifier_conflict`), and field
selection, then commits — all inside **one** Postgres transaction guarded by
`pg_advisory_xact_lock(730234)`. `merge-stage.md:24-29` states this as a
hard design constraint: "One Merge Stage transaction validates evidence and
policy, resolves identity, selects role and identity fields... No adapter,
API override, bulk loader, seed, repair, or reconciliation path writes
master state around this entry point." There is already a `preview: bool`
parameter on `apply()`, but the one place it's used today
(`merge.py:172-174`) is a duplicate-batch-key short-circuit, not a general
dry-run a steward can come back to later — nothing survives past that one
call unless it commits.

### Proposal: a persisted, reviewable pre-merge staging state

Per the operator's answer to this session's grilling question ("what should
the new stage give that the existing preview/conflict-check doesn't" →
"a persisted, reviewable staging state"):

**What it would add**: after identity matching produces a candidate merge
group (the `groups`/`state.bindings` computation inside `apply()`,
`merge.py:~207-215`) but before the atomic commit, persist one row per
candidate group into a new durable table (shape sketch, not a committed
design — e.g. `mdm_v2.merge_candidate`) capturing: member subject ids, the
conflicts already computed (`kind_conflict`, `authoritative_identifier_conflict`),
the field selections `select_fields()` would produce, the `policy_digest`,
and a status (`pending_review` / `auto_eligible` / `rejected`). This gives
Clean MDM something legacy already has and Clean MDM currently doesn't: a
queryable row a steward can inspect **asynchronously, in a separate
transaction**, the way legacy's `mdm_entity_attribute_stage`
(`resolvers/base.py`'s `stage_candidate`) lets an operator see staged
candidate field values before survivorship picks a winner — instead of only
seeing a `Conflict` raised synchronously, inline, inside one live `apply()`
call.

**Why this fits Clean MDM's own accepted policy, not just legacy's shape**:
`merge-stage.md:38-42` already requires exactly this kind of gate for
identity consolidation — "consolidating two established identities requires
an explicit steward decision... A bridge between several eligible
identities goes to review without attaching to an arbitrary winner." Right
now that review has no durable home to live in between "conflict detected"
and "steward decides" — a staging table would give it one.

**The one hard constraint this proposal must not violate** (flagged, not
resolved here): the staging write must not itself become a second path that
writes master state, which is exactly what `merge-stage.md:24-29` forbids.
A staging table only stays inside that rule if it's read-side/advisory
state — the actual identity and field commit still happens only through
`MergeStage.apply()`'s existing atomic transaction. Whether a persisted
staging table can be added without that ever being mistaken for (or
becoming) a second master-state writer is Clean MDM's call, not this map's.

**Open design questions this proposal surfaces, left to Clean MDM's owners**:

1. Does a staged-but-uncommitted candidate block, or just coexist with, a
   later `apply()` call touching the same closure? `apply()`'s only
   concurrency guard today is the single advisory lock
   (`pg_advisory_xact_lock(730234)`) — a staging table adds a second piece
   of state that lock doesn't cover.
2. Where does staged data live — alongside `mdm_v2` in `mdm`, or is any new
   table out of scope while the local-PostgreSQL-first phase is still
   proving the core (per `state-of-build.md`'s current qualification
   target)?
3. Required step (every merge must be staged first) or additive/optional
   inspection layer (`apply()` keeps working standalone)?
4. Expiry/cleanup for staged-but-rejected candidates — none of the existing
   accepted policy (Q1-Q16) speaks to this.

### Evidence

- `origin/codex/clean-mdm-integration:edgar_warehouse/mdm/clean/merge.py`
  (read live, this session)
- `docs/specs/clean-mdm/merge-stage.md` (read live, this session)
- `docs/specs/clean-mdm/state-of-build.md` (read live, this session)
- Legacy comparison:
  [agent-open-query-interface research 05](../agent-open-query-interface/research/05-mdm-postgres-ddl-inventory.md),
  [research 06](../agent-open-query-interface/research/06-mdm-postgres-call-sequence.md),
  and `edgar_warehouse/mdm/resolvers/base.py` (read live, prior turn this
  session).
