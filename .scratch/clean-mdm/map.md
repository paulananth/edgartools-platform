# Clean MDM: design, build locally, then deploy

Label: `wayfinder:map`

## Destination

Replace separate role identities with shared Company and Person identities,
governed profiles, permanent source evidence, and a shared Merge Stage. Prove
the complete core offline on PostgreSQL 16, qualify the same migrations on
Snowflake Postgres, and cut over only after consumer and rollback acceptance.

## Notes

- Current design review: [Claude handoff reconciliation](../../docs/specs/clean-mdm/design-reconciliation-2026-09-19.md).
  [Company Q1–Q12](../../docs/specs/clean-mdm/company-policy.md) are accepted.
  [Gate 08](issues/08-confirm-company-candidate-assessment.md) asks only the
  breadth of mandatory pre-application assessment persistence; resolve it
  before starting that implementation.

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
  `codex/sec-gleif-company`, rebased onto `origin/main` at `b87fc05a`.
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
