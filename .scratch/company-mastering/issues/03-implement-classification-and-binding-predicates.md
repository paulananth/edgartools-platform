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

## Resolution decisions (operator, 2026-09-23)

The ticket said "nothing to decide". Building it surfaced three, all taken one
question at a time.

1. **The Merge Stage is the system of record for mastering, and the lookup
   happens inside its transaction.** A source record resolves by looking up
   master data; it either gets back an existing entity id or a new one is
   created. The lookup and the write are never separated, so two concurrent
   runs reading the same new entity cannot both miss and both mint: one wins
   and the other sees the first one's id. Rejected: resolving in a step that
   commits before the merge, which makes duplicate ids a routine outcome to be
   consolidated afterwards.

2. **One source record describes one entity of one kind, and each entity a
   filing touches resolves on its own.** A Form 4 produces two records — the
   issuer as a Company, the reporting owner as a Person — plus the
   relationship between them. Each is looked up separately, so every
   combination is normal and must work: an existing Company with a new Person,
   a new Company with a new Person, an existing Person with a new Company.
   This is already what `adapters.normalize` and the assertion shape do; it is
   recorded because it was not written down.

3. **A new entity seen many times in one run gets one id, not one per
   record.** Forty filings by the same unknown person mint one Person, not
   forty to be consolidated later. The consequence, which is the hard part:
   to give the same id the second time, the run must match the record against
   *the pending entities of the same run*, not against master data, because
   the master data does not hold them yet. That match is made on evidence not
   yet committed, so the rule that makes it must be **the same rule** used
   against master data, held to the same bar — not a looser within-batch
   shortcut. Rejected: minting one id per record and collapsing them
   afterwards, which manufactures exactly the published-id consolidation the
   accepted policy treats as a separate, harder problem with its own gate
   (Q10, Q11).

**Terminology, for the avoidance of doubt.** *Kind* is the type — Company,
Person, Fund Structure. *Entity* is the individual thing. One source file
yields many entities, each of one kind; the kind is decided per record, never
per source (`adapters.py:77-80`). The Merge Stage already produces one master
record per entity, each listing the source records behind it; a batch is a
transaction boundary, not a unit of meaning.

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

**Closed 2026-09-23:** `profile_fields` stays at the top level, because a role
attaches to several kinds, and a profile field now records its **role's**
digest rather than the enclosing kind's. See ticket 02 decision 3's second
amendment.
