# Clean MDM: design, build locally, then deploy

Label: `wayfinder:map`

## Destination

Replace separate role identities with shared Company and Person identities,
governed profiles, permanent source evidence, and a shared Merge Stage. Prove
the complete core offline on PostgreSQL 16, qualify the same migrations on
Snowflake Postgres, and cut over only after consumer and rollback acceptance.

## Notes

- 2026-09-22: [Ticket 12](issues/12-integrate-native-gleif-company-publications.md)
  implements native GLEIF evidence and whole-publication accounting on
  `codex/company-native-gleif`, rebased through `5e2e4501` (#691). PR #673 already
  merged the earlier foundation; older stacked-branch notes below are historical.
  [Acceptance](ticket12-acceptance.md) distinguishes full JSON parser qualification
  from matching and production throughput. Next is Company Mastering Policy and
  Dataset Contract versioning, available for [Claude handover](../handover/2026-09-22-company-mastering-to-claude.md)
  after this PR lands. No automatic binding or consolidation rule has been activated.


- 2026-09-20: ticket 11 implemented on `codex/company-publication-verification`
  in `../edgartools-platform-company-publication-verification`, based on
  `codex/sec-gleif-company` at `7784c0e3`. This is an isolated stacked branch;
  the parent has not merged. [Source-publication contract](../../docs/specs/clean-mdm/source-publications.md)
  and [review](company-publication-review.md) describe the source-only fixture.
  Next: [ticket 12](issues/12-integrate-native-gleif-company-publications.md),
  native metadata/normalization, verified batch membership and consumption
  accounting. Company matching qualification remains a separate requirement.

- 2026-09-20: [Company pickup from Claude](../handover/2026-09-20-codex-company-enrichment-reconciliation.md).
  Rebased onto `dc55bf1d`; assessment foundation preserved as `f3f924a9`.
  [Ticket 10](issues/10-build-family-checkpoints.md) is verified (47 tests, no skips).
  Next: [ticket 11](issues/11-verify-enrichment-publication-inventory.md), source
  inventory/continuity verification before GLEIF consumer integration.

- Current design review: [Claude handoff reconciliation](../../docs/specs/clean-mdm/design-reconciliation-2026-09-19.md).
  [Company Q1–Q13](../../docs/specs/clean-mdm/company-policy.md) are accepted.
  [Gate 08](issues/08-confirm-company-candidate-assessment.md) is accepted:
  persist every proposed binding/consolidation before application, without
  a manual pause for qualified proposals.
  [Ticket 09](issues/09-build-company-candidate-assessment.md) implements the foundation.

- User priority, 2026-09-19: complete SEC + GLEIF multisource Company mastering
  before other entity integrations. [Company completion gate](../../docs/specs/clean-mdm/company-completion.md)
  defines the required scope and evidence; the SEC-only sample is insufficient.

- Latest handoff: [state of the build](../../docs/specs/clean-mdm/state-of-build.md).

- This map carries execution after the explicit design gates. The user's
  delivery sequence is domain model and inventory, merge/recovery contracts,
  local implementation and evidence, then target qualification and cutover.
- Use Wayfinder, domain-modeling, grilling for unresolved policy decisions,
  and the repository-required GoF review before modifying code.
- Existing source authority, single-root-run ownership, bounded atomic commit,
  GLEIF family boundaries, and SEC Bronze retention decisions remain applicable.
- The user's new shared-identity objective replaces separate role identity as
  the target here. It does not change the currently deployed system or rewrite
  the historical enrichment program's decisions.
- No implementation tickets until the Merge Stage policy gate is resolved.
  Draft specifications are proposals, never evidence of implementation.
- Interview rounds contain at most three questions (user instruction, 2026-09-18).
- Current worktree: `../edgartools-platform-sec-gleif-company`; branch:
  `codex/sec-gleif-company`, rebased onto `origin/main` at `dc55bf1d`.
  PR #657 merged the earlier integration branch at `e2807e52`, preserving
  Grok PRs #655/#656. PRs #658/#659 supply the new query ADR and Claude handoff.
  Earlier worktrees remain protected rollback anchors.
- Local PostgreSQL 16 worktree: `../edgartools-platform-grok-local-postgres`;
  DSN/provision branch: `grok/clean-mdm-local-postgres` (PR #655);
  bounded local mastering branch: `grok/local-mdm-bounded-mastering`.
- Local Postgres DSNs, start commands, and last observed state:
  [local-postgres.md](local-postgres.md).
- Inspected base: `b1babd8bbd0e04044fcacbbab822d480c97c01bc`.
- [Delivery index](../../docs/specs/clean-mdm/README.md).

## Decisions so far

- [Compare vendor match, survivorship, and merge-reversal rules](issues/02-research-vendor-merge-rules.md)
  — primary-source comparison separates source binding, consolidation and
  field selection; revises unsupported threshold and survivor-ID proposals.
- [Apply current MDM schema to local PostgreSQL 16](issues/03-apply-current-mdm-schema-to-local-postgres.md)
  — historical prerequisite checkpoint: schema (38 tables, migrations 001–022) on
  PostgreSQL 16.15 at `127.0.0.1:5432/mdm`; domain golden records empty except
  10 seeded audit firms; Clean MDM shared-identity tables were not created.

The ongoing [identity, merge, and recovery policy interview](issues/01-set-merge-stage-policy.md)
records acceptance of Q1–Q16 on 2026-09-18. The gate is resolved; unqualified
automatic binding stays disabled while local implementation proceeds.

## Not yet specified

- Detailed adapter schemas and acceptance fixtures follow the policy gate.
- Target qualification must resolve actual Snowflake Postgres privileges and
  version compatibility, pinned source inventory, consumer migration manifest,
  before activation. The user selected local PostgreSQL for the current target
  and a 30-day legacy rollback window; Snowflake qualification is deferred.
- Exact resource sizing and scheduling follow measured accepted workloads.

## Out of scope

- SEC acquisition or Bronze retention redesign, Snowflake silver changes,
  unrelated gold analytics, non-AWS deployment, and new conditional-source
  licensing or purchase.
- Destruction of legacy MDM or activation based on local tests alone.

## Q16 resolution — 2026-09-18

The user accepted starting the offline build with unqualified automatic rules
disabled. This supersedes earlier pre-implementation calibration timing above.
Q1–Q16 are accepted; numeric calibration and versioned policy evidence are
mandatory before each automatic rule activation. Implementation is authorized;
production activation still requires all local and hosted acceptance gates.

Implementation begins with [the isolated PostgreSQL foundation](issues/03-build-postgres-foundation.md). The dependent implementation tickets cover merge/recovery, pipeline integration, consumer contracts and hosted qualification.

- [Build the isolated PostgreSQL foundation](issues/03-build-postgres-foundation.md): real migrations, restricted writes, atomic checkpoints and outbox, and three-database journal mirroring verified locally.
