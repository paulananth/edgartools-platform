# Define role grants for capture worker, publication coordinator, domain publisher, steward, Release Owner, retention operator

Type: grilling
Status: resolved
Blocked by: none (05 resolved)

## Question

The GoF review's Appendix C item 6: role grants for the six roles it names
(capture worker, publication coordinator, domain publisher, steward,
Release Owner, retention operator).

Facts found before asking: `change_ledger` (migration 013) already has five
`NOLOGIN` roles the application enters with `SET ROLE`, each with
column-scoped table grants and nothing for `PUBLIC`:
`edgartools_acquisition_coordinator`, `_worker`, `_processor`,
`_silver_finalizer`, `_operator`. Clean MDM (`mdm_v2`, migration 023 +
`clean/store.py` `migrate()`) has one restricted runtime role with no
table-write privilege at all; it may only execute `commit_batch` /
`record_attempt`. A decision's actor and reason live *inside* the decision
body — `commit_batch` rejects a decision without them — so stewardship is
an application actor, not a Postgres role.

## Comments

- 2026-09-19, Q1: operator chose **(a)** — no new Postgres roles.
- 2026-09-19, Q2: operator asked for business-friendly names for the five
  `SET ROLE` roles. Proposed seven names (five ledger + two MDM-side);
  operator asked whether Publication Verifier is the pre-merge stage —
  clarified no: Publication Verifier is file-grained in the Change Ledger
  (are all files for this publication present and verified) and gates the
  consumer *starting*; the pre-merge stage is record→entity-grained in
  MDM (which existing entity does this record join), inside the consumer,
  before `commit_batch`. Operator: "names are fine."

## Answer

**No new Postgres roles.** GLEIF capture runs under the five existing
`change_ledger` roles; its consumer runs under Clean MDM's runtime role;
Steward and Release Owner are actors recorded in the decision, not
database roles. The spec uses the business names below everywhere and
shows the technical alias once, in this table.

| Business name | Technical alias | Does |
| --- | --- | --- |
| **Fetch Planner** | `edgartools_acquisition_coordinator` | Decides which source files to get; records the Change Ledger Fetch Decision |
| **Source Capturer** | `edgartools_acquisition_worker` | Downloads a file, verifies its hash, records the capture |
| **Revision Claimer** | `edgartools_acquisition_processor` | Marks a verified Logical Source Revision "being processed" so it is processed once |
| **Publication Verifier** | `edgartools_acquisition_silver_finalizer` | Records that a publication's expected outputs were produced and verified complete, or failed — the gate that lets a consumer start (ticket 05 completeness, ticket 06 step 2) |
| **Ledger Repairer** | `edgartools_acquisition_operator` | Human-driven repair: quarantine, exclusion, superseded-artifact deletion evidence (the GoF "retention operator"; the S3 delete itself is IAM, not Postgres) |
| **MDM Committer** | Clean MDM runtime role, via `commit_batch` | The only path that writes master tables, one atomic batch at a time (the GoF "domain publisher") |
| **Steward** | `actor` field in the decision body | The person or deterministic rule that made a match/merge/override decision; enforced by `commit_batch` requiring actor + reason |

GoF's "Release Owner" is a person approving a consumer's release evidence
(parent program's per-consumer release gate) — not a runtime role and not
in this table.

Grain reminder for the spec: Publication Verifier is file-grained and
precedes the consumer; the pre-merge candidate table (already proposed to
Codex) is record→entity-grained and sits inside the consumer, after
matching and before the MDM Committer.
