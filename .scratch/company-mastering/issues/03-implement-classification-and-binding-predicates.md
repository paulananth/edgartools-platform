# Implement classification and the binding predicates in the Merge Stage

Type: task
Status: in progress — the versioning seam is built; the predicates are not
Blocked by: 02

## Question

Nothing to decide once 01 and 02 land. Implement the policy runtime inside the
**existing** Merge Stage and assessment transaction. Do not build a second
merger, and do not add a source-specific matcher.

- Evaluate the policy's named, versioned primitives: classification per source
  record, candidate predicates, field rules.
- Replace the blanket refusal (`store.py:162`, `merge.py:303`) with the
  implemented predicates, so an unimplemented or unapproved rule is still
  refused, by name, with its reason.
- Keep null, clear and retract semantics, provenance per value, and Q13's
  pre-commit assessment for every proposed binding.
- TDD at the policy and transaction seams, then real PostgreSQL 16.

Proves: reordered and duplicate input, stale assessment rejection, lost
acknowledgement, retained field conflicts, reversal of an incorrect merge, and
a stable surviving ID.

## Built, 2026-09-22 (`6cc6ee09`, `44903e41`)

The versioning seam tickets 01 and 02 amended, which the predicates rest on:

- migration 031 — `mapping_version` in the hashed body and a lifted `bigint`
  column, the widened publication uniqueness rule, `mdm_v2.dataset_mapping`,
  and the assertion write patched through `pg_get_functiondef` with
  exact-fragment guards (migration 029's pattern);
- the revision guard re-keyed to `(revision, mapping_version)`;
- a kind's field rules readable at `kinds.<kind>.fields` through one resolver,
  old-shape bodies still working, a body carrying both refused at
  registration; a selected field records its kind's digest with the kind
  version beside it;
- `register_dataset` compares the protected parts itself and registers a new
  reading; both adapter entry points resolve the reading and its body through
  one accessor and stamp it on the record.

Tested against real PostgreSQL 16, including a populated-store migration
pass, and through both Company evidence sources' real contracts.

**The safety net is still in place**: `store.py` and `merge.py` still refuse
every `automatic_rules` body, and the test that proves it is untouched.

## Still to build

The predicates themselves: the named versioned primitives and their registry,
classification per source record, the binding predicates that replace the
blanket refusal, the activation bar per `(kind, family)`, the suspension table
(keyed and scoped per ticket 02's amendment), and group-aware selection.

Two things the build surfaced, for whoever takes them:

- `030_clean_mdm_evidence_disposition.sql:26-27` still checks a deferred
  record's `schema_version` against `mdm_v2.dataset`, which is frozen at
  reading 1, while the assertion path now checks the reading's own body. Under
  a corrected mapping an assertion is accepted and the deferred record from
  the same read is refused.
- `kind_digest` covers the whole `kinds.<kind>` block. Once classification and
  binding rules live in that block, editing one will move every field's
  recorded digest, which is the churn ticket 02 decision 3 exists to stop,
  reappearing inside one kind. Narrowing it to the authority-bearing sub-block
  is cheap now and expensive later, because no production policy carries a
  `kinds` block yet.
