# Ticket 11 review — source-only publication verification

Date: 2026-09-20. Base: `codex/sec-gleif-company` at `7784c0e3`.
Branch: `codex/company-publication-verification` in its dedicated worktree.

## GoF review

Applied the available `gof-refactor-reviewer` skill before implementation and
again during diff review. Inspected `clean/cli.py`, `clean/adapters.py`,
`acquisition/revisions.py`, acquisition ledger migrations and their history
(`7784c0e3`, `e2807e52`, `82aa5c50`, `7e58406c`). No repeated variation justified
a Strategy/Factory hierarchy or refactoring the existing acquisition lifecycle.
The focused verifier accepts a first-class artifact opener, reuses the existing
ledger and dataset authority, and keeps recovery planning free of database writes.
No broad structural refactor recommended.

## Standards and contract review

- No existing migration changed; no new table, role, grant or root-run identity.
- Python executed through uv. Tests use real PostgreSQL 16 migrations and
  restricted logins in separate acquisition and MDM databases, without skips.
- Acquisition UUIDs retained as lineage but excluded from source inventory
  content digest; fixture pins expected normalized assertions and hashes.
- Native manifest members resolve by logical source key; publishers need no
  internal database IDs. Extra/conflicting revisions and duplicate identities fail.
- Evidence requires both immutable revision and matching CAPTURED transition;
  even an injected processor-owned row without capture is rejected.
- File availability and raw hashes are checked on every verification. Canonical
  and domain hashes are checked against pinned interpretations, not invented by
  the verifier. Artifact stream reads are bounded and readers are injected.
- Recovery requires exact predecessor sequence/hash, advances source sequence,
  rejects sibling scopes and native identity conflicts, and has deterministic
  byte-cost/count/hash tie breaking. Full reconciliation is the fallback only.
- MDM rollback leaves acquisition evidence intact; successful retry retains proof
  with its own family checkpoint. Required downstream receipts remain pending.
- The generic manifest runner still accepts caller proof metadata; this API is
  not yet its authentication boundary. Native consumer wiring and membership /
  whole-publication accounting are explicit ticket 12 requirements.

## Limits

Synthetic source-only verification does not qualify native GLEIF formats, full
source volumes, hosted IAM, complete Company mastering or automatic matching.
Derived/reinterpreted revision lineage is rejected in v1. A returned object is an
in-process proof, not a signed capability. A previous fully consumed publication
is a caller precondition until the consumer's accounting integration exists.
The whole shared-foundation release gate remains broader than ticket 11.

Review was performed in this Codex session; no independent-agent review is claimed.
Acceptance results and source hashes are in `company-publication-acceptance.json`.
