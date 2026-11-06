# Confirm relationships before showing them

Operator ruling: only real relationships, never possible relationships. Check
Government Entity and International Organization before adding anything.
The operator then included Fund Series and requested the rule in the skills.

- [x] Read the current shared MDM in read-only repeatable-read snapshots:
  both kinds have zero current masters and zero retained identities; the
  governed current/evidence stores have zero relationship records
  (2026-11-05 21:42 ET). Legacy tables were not used as proof.
- [x] Replace instructions to draw permitted endpoint types with a
  source-neutral evidence requirement in the catalog, modeling and destination
  skills (2026-11-05 21:42 ET).
- [x] Remove the two subjects' unsupported catalog-owned graph edges:
  16 domain/type and 8 glossary/type edges removed. Native readback matched;
  unrelated graphs were preserved and a repeat removed zero
  (2026-11-05 21:46 ET).
- [x] Check Fund Series: the current shared store holds 12,937 Fund Structure
  masters and retained identities, but no retained relationships. Its approved
  glossary definition and placement are correct. Remove 12 unsupported
  domain/type and 5 glossary/type edges; native readback matched and unrelated
  graphs were preserved (2026-11-05 21:48 ET).
- [x] Restore the Government Entity display name and domain definition from
  the existing CONTEXT.md meaning, with matching native readback. No business
  definition or master record changed (2026-11-05 21:48 ET).
- [x] Validate skills with genericity and existing-path checks: 98 passed
  (2026-11-05 21:49 ET).
- [x] Repeat the full three-subject repair: zero further removals, matching
  native readback and unchanged unrelated graph metadata
  (2026-11-05 21:49 ET).
- [x] Publish the skill correction and operational record in PR
  https://github.com/paulananth/edgartools-platform/pull/1448, ready for review
  (2026-11-05 21:50 ET). CI remains required before merge.
- [x] Correct the overly narrow Fund conclusion after investigating the local
  N-PORT store: normal retained-reading and canonical master lookups verified
  12,937 reported series/registrant pairs resolving to 1,245 Company masters,
  zero unresolved. These are source-reported associations, not active mastered
  `IS_SUBFUND_OF` links; the existing start-date ruling remains in force
  (2026-11-05 22:16 ET).
- [x] Verify the selected local PostgreSQL 16 container is running and its
  port matches the private MDM connection. N-PORT fund and registrant runs are
  complete; no N-PORT Security run or physical `nport_holding` table exists in
  this environment. Holdings cannot be claimed as landed here
  (2026-11-05 22:16 ET).
- [x] Reproduce a second publisher defect on invented input: a comment-only
  reference to a deferred type makes `_codes_read` report that type as read.
  A text mention is therefore not execution evidence (2026-11-05 22:16 ET).
- [ ] Correct the publisher's runtime projection before another normal
  publication. The current configuration-only plan still emits permitted
  domain/type and glossary/type edges; this documentation change does not
  implement a runtime guard or a confirmed-record projection. Tracked in
  https://github.com/paulananth/edgartools-platform/issues/1447.
- [ ] Project the verified reported series/registrant associations separately
  from active mastered links, and preserve the transaction nature of holdings.
  The first scoped repair removed possible-type edges, but did not supply this
  missing projection. Included in issue 1447.
- [x] Learning → skill: `skills/data-catalog/SKILL.md`, "Confirm relationships
  before showing them", owns the evidence method. The destination skill
  carries scoped repair and the publisher capability boundary
  (2026-11-05 21:42 ET).

## Review: Standards

Skills and an aggregate operational record only. No source values, credentials,
database writes or provider requests. Source-independent instructions preserve
the vocabulary and distinguish absent evidence from unknown evidence.

## Review: Spec

The operator's latest ruling replaces the earlier instruction to draw possible
relationships. The initial inference that no mastered records meant no real
Fund connections was too broad. Retained N-PORT readings establish reported
series/registrant associations, even while the mastered link is deferred.
The skills now require all applicable evidence layers and honest labels.
Normal publication and the reported-association projection remain capability gaps.

## Review: GoF

The skill is available and was consulted. Existing publisher history uses
plain projection and native API functions. No program changes or pattern
refactor are part of this skill correction.
