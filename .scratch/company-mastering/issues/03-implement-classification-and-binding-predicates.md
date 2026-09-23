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

## Also built, 2026-09-23

The three issues the build surfaced are closed:

- migration 032 checks a deferred record's `schema_version` against any
  registered reading, so a deferred record and an assertion from one read now
  agree. The reading is deliberately **not** added to the deferred body: its
  natural key is `(source_code, publication_key, record_locator)` (migration
  027), which a re-read reuses, so a second body carrying a reading would
  collide with the first under `030`'s read-back comparison rather than sit
  beside it. A deferred record is evidence that a record could not be read;
  the schema it was read under identifies its contract;
- the kind digest is narrowed to the authority-bearing sections, named in
  `survivorship.AUTHORITY_SECTIONS`, with an undeclared section refused by
  name (ticket 02 decision 3, amended);
- the real Company policy moved to `kinds.company`, with its own authored kind
  version, so the per-kind digest and the kind version are delivered for the
  one policy that matters rather than only in tests.

**Still open, and now the oldest thing here:** the blocking disposition of a
deferred record reads `nonblocking_deferred_reasons` from the frozen
`mdm_v2.dataset` row in three places — `030:35`, `030:59` and `merge.py:495`
in Python. That field is not a protected part, so a corrected mapping may
legally change it and none of the three would see it. The three agree with
each other today, so nothing is broken; fixing it means changing all three
together, and it belongs with whoever next touches the deferred path.

Also still open, from the review: `profile_fields` sits at the top level,
outside the digested block, so editing a profile role's rules changes no
recorded digest at all — the mirror image of the churn fixed above. It belongs
with whichever ticket moves `profile_fields` under `kinds.<kind>`.
