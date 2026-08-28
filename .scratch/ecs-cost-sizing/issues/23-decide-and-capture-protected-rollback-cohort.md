# Decide and Capture the Protected Rollback Cohort

Type: grilling
Status: resolved
Blocked by:

## Question

Which exact six warehouse/MDM task definitions and immutable image digests are
the protected production rollback cohort, and what evidence is required before
cleanup may rely on that designation?

Research rejected the last captured pre-handoff live cohort:
warehouse `small:159`, `medium:164`, and `large:157` on digest
`sha256:a493e0d183f4bd1d5a01f46034b2250d76830206b49672b5f14d9a35080e504e`,
plus MDM `small:137`, `medium:138`, and `large:72` on digest
`sha256:cc64ba854ee382256fe7f58381f57feadd923645507bac53cf7e0c57a4e4640a`.
Both digests retain immutable role/source tags, but the only execution in their
exact deployment window failed before graph and gold completion, and both
images predate production-observed fixes. They are recovery evidence, not an
approved known-good release.

Decide between these evidence-backed choices:

1. Persist the current six revisions as the release baseline and retain one
   canonically identical earlier six-revision cohort (`164/168/161` warehouse,
   `141/141/75` MDM) as control-plane recovery, explicitly acknowledging that
   it is not an independent code rollback.
2. Build and rehearse a separate immutable post-fix image pair through the
   bounded full-chain contract before designating it as a code rollback.

Persist the decision with exact ARNs, digests, role source commits/tags,
generated-definition compatibility, evidence hashes, and an operator
attestation. Revision adjacency or `latest-N` is not acceptable rollback
evidence.

## Answer

The two options in this ticket's own text turn out not to be a strict
either/or — they answer two different questions, per Ticket 04's own
Configuration-Rollback-vs-Code-Rollback distinction. **Option 1 adopted
now** (Configuration Rollback, cheap, available immediately); **Option 2
split into a new follow-up task** (Code Rollback, real future work, not a
blocker). This satisfies Ticket 19's Wave 0 hard prerequisite — the
rollout may now proceed.

### Current release baseline (captured live, 2026-08-13 — not the stale
2026-08-09 snapshot elsewhere on this map; several deploys landed this
session since then)

Confirmed by cross-checking `describe-task-definition` against the live
ASL of `load_history`, `daily_incremental`, `gold_refresh`,
`residual_holds_graph`, `mdm_utility`, and `load_daily_form_index_for_date`
— every one resolves to exactly these six revisions, no drift found:

| Task family | Revision | CPU/Mem | Image digest | Tags | Pushed |
| --- | --- | --- | --- | --- | --- |
| `edgartools-prod-small` | 181 | 512/1024 | `sha256:64ff30ae...` | `warehouse-prod`, `warehouse-sha-3cd8e60a456a` | 2026-08-12T07:23:28-04:00 |
| `edgartools-prod-medium` | 186 | 1024/4096 | `sha256:64ff30ae...` | (same) | (same) |
| `edgartools-prod-large` | 178 | 2048/8192 | `sha256:64ff30ae...` | (same) | (same) |
| `edgartools-prod-mdm-small` | 158 | 512/1024 | `sha256:ac245df9...` | `mdm-prod`, `retain-mdm-current`, `mdm-sha-c137ebc4ab44` | 2026-08-11T12:51:56-04:00 |
| `edgartools-prod-mdm-medium` | 158 | 1024/4096 | `sha256:ac245df9...` | (same) | (same) |
| `edgartools-prod-mdm-large` | 92 | 2048/8192 | `sha256:ac245df9...` | (same) | (same) |

**Persisted as the release baseline.**

### Configuration Rollback cohort (Option 1)

Confirmed live, all six revisions still `ACTIVE` (not deregistered) and
CPU/memory still exactly matching the current tier definitions — genuinely
canonically identical, not just claimed:

| Task family | Revision | CPU/Mem | Status |
| --- | --- | --- | --- |
| `edgartools-prod-small` | 164 | 512/1024 | ACTIVE |
| `edgartools-prod-medium` | 168 | 1024/4096 | ACTIVE |
| `edgartools-prod-large` | 161 | 2048/8192 | ACTIVE |
| `edgartools-prod-mdm-small` | 141 | 512/1024 | ACTIVE |
| `edgartools-prod-mdm-medium` | 141 | 1024/4096 | ACTIVE |
| `edgartools-prod-mdm-large` | 75 | 2048/8192 | ACTIVE |

**Persisted as the Configuration Rollback candidate, explicitly not an
independent Code Rollback** — same code generation, older wiring/revision
only. Protects against a bad configuration/wiring change (the kind Waves
1, 2, 3, and 5 of Ticket 19's rollout mostly produce); does not protect
against a code regression already present in both cohorts.

**Operator attestation**: pending — this ticket captures and persists the
evidence; the sign-off itself is the operator's action, not something this
ticket can self-certify.

### Code Rollback (Option 2) — split to a new task, not a blocker

Ticket 24 already confirmed nothing today qualifies: the only pre-handoff
execution in the exact prior registration window failed at `mdm export`
and never validated `BatchSilver` children, graph, or gold completion.
Building a genuinely validated Code Rollback cohort — a separately
attested, actually-rehearsed prior image pair — is real work, not a quick
capture. Split into [Ticket 32](32-build-and-rehearse-code-rollback-cohort.md).
Not a blocker for Wave 0: genuinely new *code* risk (versus config/wiring
risk) is primarily Wave 4's (machine-profile) concern, and Ticket 04's own
policy already leans on Configuration Rollback's 15-minute restore as the
fast primary safety net even there.
