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

## Checklist

Kept current per the task-checklist rule (CLAUDE.md, 2026-09-24). Times are
local ET; parts finished before the rule existed carry their date only.

- [x] Versioning seam: migration 031, revision guard re-keyed, per-kind field
  rules — `6cc6ee09`, `44903e41`, PG16 (2026-09-22, time not recorded)
- [x] Deferred record checks its reading (migration 032); kind digest narrowed
  to authority sections; Company policy under `kinds.company` — PG16
  (2026-09-23, time not recorded)
- [x] Profile field records its role's digest — #696 (2026-09-23)
- [x] Per-kind Stage and Master views — #699, #700 (2026-09-23)
- [x] `classify` reports the step that fired; one well-formedness check shared
  by registration and evaluation (`classification.check_rule`) — unit tests
  (2026-09-24 07:05 ET)
- [x] Registration checks §10 1, 2, 6 and 9 (`activation.check_policy`,
  `rule_version_conflicts`) — unit + PG16 (2026-09-24 07:20 ET)
- [x] Blanket `automatic_rules` refusal replaced by the §9.2 measured
  activation check, at registration and again per batch; accepted bar floors
  per kind (Company 99.9% at 95%, Person 99% at 97.5%) — unit + PG16
  (2026-09-24 07:20 ET)
- [x] Read path runs the rule a Dataset Contract names; rule id, version and
  step recorded in the hashed provenance; an unactivated or non-kind verdict
  is set aside with its rule — unit + PG16 (2026-09-24 07:15 ET)
- [x] Four operator-picked Companies (AAPL, MSFT, Shell, ASML) from real SEC
  bronze and the pinned GLEIF golden copy, plus two individual controls — PG16
  `test_clean_four_companies.py` (2026-09-24 07:18 ET)
- [x] Three-axis `/code-review` of this branch — Standards: no hard
  violation; Spec: 5 gaps, 3 implementation issues; GoF: leave, one reshaping
  for ticket 04 (2026-09-24 07:25 ET)
- [x] Review fixes: read path checks the policy before trusting an activation
  and fails before its first record; §9.2 tolerance accepts the spec's own
  five-decimal example and refuses a bound rounded up; a rule written for
  another `source` is refused; spec note corrected (check 9 is
  registration-only, compares the whole rule, deliberately) — unit + PG16
  (2026-09-24 07:25 ET)
- [ ] ~~`evaluated_per` (one verdict per key, shared by every record carrying
  it)~~ not built: each record is classified on its own row today; needed
  before a Form 4 owner's many records can share one verdict
- [ ] ~~`evidence_recorded` (source category, asserted legal form and inferred
  kind stored separately)~~ not built; provenance carries rule, version, step
- [ ] ~~Check 1 for primitive arguments~~ arguments are still checked when a
  record reaches the primitive, not at registration
- [ ] ~~Reshape `_check_activation` into shared resolve plus a per-activation
  check~~ first commit of ticket 04 (GoF review): its `verdict not in KINDS`
  line would refuse every `bind` activation
- [x] ~~Decide: `classification_*` deferred reasons block~~ superseded by
  the confidence-bands decision above (2026-09-24 08:14 ET)
- [x] PR opened and CI green — #704, merged 2026-09-24 07:37 ET (merge time
  from GitHub; checklist ticked at 08:14 ET)
- [x] Decide how a set-aside record blocks — operator, 2026-09-24 08:14 ET:
  confidence bands (≥95% acts, 50-95% waits in the Stage unreviewed, <50%
  goes to a Steward), recorded in the Company policy
- [ ] `company_stage` shows the latest row per company per source; a
  separate history view keeps every version — operator (2026-09-24 08:28 ET)
- [ ] Implement the bands: Company accepted bar 0.999 → 0.95 in
  `activation.ACCEPTED_BARS`; per-step measured probability on each rule
  step; 50-95% verdicts non-blocking in the Stage; <50% blocking for a Steward
- [ ] Binding predicates replacing the binding refusal — needs ticket 04's
  identifier primitives; binding rules and `deterministic` activation are
  refused by name until then
- [ ] Merge Stage mints entity ids inside its transaction (ADR 0013), shipped
  together with widening `assessment_snapshot` to the candidate key
- [ ] Suspension table keyed `(policy_digest, kind, family, rule_id,
  rule_version)`, scoped to §9.3 deterministic verdicts
- [ ] Group-aware field selection (`field_group`)
- [ ] ~~Measured proof for the SEC Company classification rule~~ deferred to
  the Proving Run (ticket 05) and activation approval (ticket 06): the rule in
  the four-company test is a candidate carrying a fixture proof
- [ ] ~~Fix the warehouse demoting every SEC `entityType: "other"` filer to
  `non_company`~~ reported to the operator, not in this ticket: found by
  reading `is_reporting_company_entity_type`, not by a live check
- [ ] ~~Registration check 3 (declared lists valid under their normalizer)~~
  not built; no registered policy carries a declared list yet

## Resolution decisions (operator, 2026-09-23)

The ticket said "nothing to decide". Building it surfaced six, all taken one
question at a time. Decisions 1 and 3 were then **challenged against the
runtime** ([03-04 challenge](../research/03-04-challenge.md)) and both need
amending before the code lands; see "What the challenge found" below.

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

4. **Classification runs at read time** (operator, Q of 2026-09-23). The
   Mastering Policy is resolved beside the Dataset Contract when the source is
   read, and the rule the contract names decides the kind. The decided kind is
   hashed into `assertion_id` (`evidence.py:80-104`), so it is settled when the
   record is read and never afterwards.

   Rejected: deciding the kind in the Merge Stage, which the hash forbids; and
   leaving the Dataset Contract's lookup table in charge (`adapters.py:77-84`),
   under which the measured rules never run and an SEC reporting owner whose
   only evidence is a name is never classified.

   `manifest["policy_digest"]` is already at the manifest's top level
   (`tests/fixtures/clean_mdm/v1/manifest.json:197`), so the read path can
   reach the pinned policy without a new input.

5. **A rule version names one exact set of steps, always, with no testing
   switch** (operator, 2026-09-23). Registration refuses a policy whose rule
   reuses a `(kind, rule_id, version)` that an already-registered policy holds
   with **different steps**. The record also carries the rule id, version and
   the step that fired, which `policy-language.md:210-213` already asks for and
   nothing does.

   Why this is not a constraint on testing: a new version is already free and
   instant. Nothing is ever overwritten — a changed body is simply a new
   digest that sits beside the old one, so a tester may register fifty. The
   check refuses one narrow case only: two different sets of steps sharing one
   version name. Working freely while testing costs one edit to a version
   string.

   Why not a switch for test environments: records written during a test are
   real records in a real store, so a reused version corrupts the test's own
   evidence. And this platform's own operating notes have the general rule —
   a check that can silently not run makes a failure and a success look
   identical.

   Where the flexibility properly belongs: the **Rules Database**, which holds
   every version with its lifecycle state (draft, proven, active, retired) and
   hands Clean MDM an *active* version. `CONTEXT.md:84-86` says explicitly to
   avoid "editing rules in the production MDM database". That database is not
   built, and building it is Codex's Source Contract area, not this ticket. If
   a draft state is ever wanted, it goes there rather than behind a flag here.

6. **The record keeps the rule that labelled it, in its provenance, inside the
   hashed body** (operator, 2026-09-23). An assertion's `provenance` block
   gains the rule id, the version and the step that fired, which
   `policy-language.md:210-213` already asks for. `provenance` is part of the
   hashed body (`evidence.py:80-104`), so the record explains itself with no
   lookup elsewhere.

   **This costs no churn, which is why it can go in the hash.** The usual
   objection — change the thing and every record gets a new identity though
   its claim did not change — is the defect fixed twice already. It does not
   arise here. The recorded rule can change in exactly three ways, and none
   adds a row that something else was not already adding:

   - the Dataset Contract points at a different rule version, which is a
     contract change, which already mints a new mapping version and so a new
     assertion id (ticket 01);
   - the same version carries different steps, which decision 5 refuses at
     registration;
   - the step that fired changes, which it cannot do on its own: the step is a
     function of the rule and the record, so fixing both fixes the step.

   Rejected: a separate table outside the hash. It keeps the fingerprint
   untouched but costs a join to answer "what labelled this?", and it breaks
   the self-describing-evidence property the versioning work established.

   **The price, stated plainly.** Records written before this lands carry no
   rule identity and are immutable, so there will be a population labelled by
   the Dataset Contract's lookup table and unable to say so. Absence means
   "decided by the adapter's table, before governed rules existed" — the same
   convention as an absent mapping version meaning reading 1
   (`evidence.py:97-106`).

## What the challenge found, 2026-09-23

[03-04 challenge](../research/03-04-challenge.md): **7 sound, 4 unsound.**
Three findings bear on what gets built next.

- **Nothing pins a rule body to its `(rule_id, version)`, and the assertion
  records no rule identity.** `register_policy` (`store.py:167-190`) runs two
  checks and never walks a rule; none of `policy-language.md:400-412`'s eight
  registration checks exist. `evidence.assertion` hashes only `kind`, where
  `policy-language.md:210-213` requires the rule id, version and step that
  fired. So two digests can hold `C-J@2026-09-20` with different steps and a
  record classifies differently with no trace. Decision 5 above answers this.

  **The per-kind digest cannot serve as the pin.** `rules` is in
  `NON_AUTHORITY_SECTIONS` (`survivorship.py`) on purpose, so a classification
  edit does not churn every field's recorded digest — which guarantees it will
  *not* move when a rule changes. Both decisions are right alone and together
  they leave the gap; the pin needs its own mechanism.

- **Decision 1's concurrency guarantee is false for the case it describes.**
  Two runs reading two *different* records of one new entity both mint: the
  assessment scope is keyed on subjects (`merge.py:311-319`), so neither
  snapshot moves, and `merge.py:353-355` only catches a duplicate `entity_id`,
  which two fresh mints are not. The guarantee holds only for the same record.
  Decision 1 and Q13 do compose; the phrasing described a protection that does
  not exist. The fix is widening the assessment scope to the candidate key —
  a change to `assessment_snapshot` (migration 028), not to where the lookup
  sits.

- **Entity ids are minted by the caller, not the Merge Stage.** There is no
  `uuid4()` in the merge path; `merge.py:353-367` only validates ids passed in.
  Decision 1 says the Merge Stage is the system of record, so either it starts
  minting or the caller's mint becomes provably safe inside the transaction.

Two more for the operator's eye: ticket 02's suspension key omits `namespace`
while that same decision counts per `(kind, namespace)` — the collapse it
warned against, inherited by ticket 04. And ticket 04's implementation surface
is zero today: no `identifier_match@1` or `identifier_cardinality@1` exists.

One correction to this ticket's own record: `otherwise: true` was described as
a judgement call against the prototype. It is not — `policy-language.md:205-207`
mandates it and §10 check 2 requires exactly one per rule. The committed
`policy-person.json` is stale against its own spec. The `token_match` refusal
is a real judgement call and it stands.

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
