# Clean MDM: design, build locally, then deploy

Label: `wayfinder:map`

## Destination

Replace separate role identities with shared Company and Person identities,
governed profiles, permanent source evidence, and a shared Merge Stage. Prove
the complete core offline on PostgreSQL 16, qualify the same migrations on
Snowflake Postgres, and cut over only after consumer and rollback acceptance.

## Notes

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
- Worktree: `../edgartools-platform-clean-mdm`; branch: `codex/clean-mdm`.
- Local PostgreSQL 16 worktree: `../edgartools-platform-grok-local-postgres`;
  branch: `grok/clean-mdm-local-postgres`.
- Local Postgres DSNs, start commands, and last observed state:
  [local-postgres.md](local-postgres.md).
- Inspected base: `b1babd8bbd0e04044fcacbbab822d480c97c01bc`.
- [Delivery index](../../docs/specs/clean-mdm/README.md).

## Decisions so far

- [Compare vendor match, survivorship, and merge-reversal rules](issues/02-research-vendor-merge-rules.md)
  — primary-source comparison separates source binding, consolidation and
  field selection; revises unsupported threshold and survivor-ID proposals.
- [Apply current MDM schema to local PostgreSQL 16](issues/03-apply-current-mdm-schema-to-local-postgres.md)
  — current runtime schema (38 tables, migrations 001–022) is live on
  PostgreSQL 16.15 at `127.0.0.1:5432/mdm`; domain golden records empty except
  10 seeded audit firms; Clean MDM shared-identity tables were not created.

No new human policy decision has been accepted. Shared identities, an isolated
rebuild, offline PostgreSQL acceptance, and delivery order remain user-directed.

## Not yet specified

- Detailed adapter schemas and acceptance fixtures follow the policy gate.
- Target qualification must resolve actual Snowflake Postgres privileges and
  version compatibility, pinned source inventory, consumer migration manifest,
  and the release owner's rollback window before activation.
- Exact resource sizing and scheduling follow measured accepted workloads.

## Out of scope

- SEC acquisition or Bronze retention redesign, Snowflake silver changes,
  unrelated gold analytics, non-AWS deployment, and new conditional-source
  licensing or purchase.
- Destruction of legacy MDM or activation based on local tests alone.
