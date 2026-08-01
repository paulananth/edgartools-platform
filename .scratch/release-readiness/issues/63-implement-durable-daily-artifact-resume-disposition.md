# Implement durable Daily-Artifact resume and disposition

Type: task
Status: open
Blocked by: (none — Decide a Durable Daily-Artifact Resume and Disposition Contract resolved)

## Goal

Implement the accepted run-bound daily-artifact manifest and append-only
per-accession outcome ledger so an interrupted daily run resumes only
outstanding work without weakening byte-exact immutable capture.

## Scope

1. Persist an immutable manifest binding run identity, ordered daily-index
   inputs, canonical accessions, warehouse image identity, and relevant
   parser/configuration versions before artifact processing.
2. Persist append-only, accession-scoped outcome records with the accepted
   disposition vocabulary and bounded candidate retry accounting.
3. Make the daily state-machine/task retry path resume from the original run
   manifest, selecting only pending, retryable, or explicitly
   repair-authorized candidates; completed candidates must never be refetched.
4. Add an operator repair-attestation flow for immutable-content conflicts.
   It must bind the candidate and conflict evidence to the original run and
   make replay explicit; it must not bypass the immutable-object guard.
5. Preserve the canonical Silver publication boundary: incomplete or
   unresolved manifests fail closed and cannot publish or satisfy the
   six-hour full-chain gate.

## Acceptance

- Focused tests prove manifest identity cannot drift on resume, completed
  candidates are skipped, and every original candidate is accounted for.
- Focused tests distinguish candidate transient retry, terminal repair, and
  task-infrastructure retry; unknown failures fail closed.
- Focused tests prove only a valid repair attestation authorizes a repaired
  candidate replay under the original run identity.
- Immutable-image production evidence demonstrates a controlled partial run,
  resume without refetching completed accessions, and fail-closed unresolved
  outcome behavior. It records manifest/ledger/attestation evidence without
  secrets.
- Schedule activation remains separately gated by full-chain evidence within
  six hours.
