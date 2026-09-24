# Prove identifier-only Company binding through a verified Identifier Contract

Type: task
Status: in progress
Blocked by: 03

## Question

Company Q14. An exact, compatible identifier resolving to **one** Company
reuses that immutable Company ID, with no separate precision study. Implement
and prove it for the SEC CIK and the GLEIF LEI:

- declare the namespace, issuing authority, normalization and primitive
  versions, scope and cardinality, and the compatibility checks, in the pinned
  policy;
- verify the contract to activate the rule (verification, not a statistical
  gate);
- an identifier that is missing, ambiguous, conflicting, suspended or of an
  unsupported namespace **defers**; it never binds;
- an LEI never establishes a CIK crosswalk merely because both values exist;
- a name change or a lapsed registration alone never revokes a binding (Q9).

Fuzzy binding and published-ID consolidation stay refused here: they keep
their own statistical gates.

## Checklist

Kept current per the task-checklist rule (CLAUDE.md). Times are local ET.
Business name: a **matching rule** (operator, 2026-09-24); "binding" in code.

- [x] Reshape `activation._check_activation` into a shared resolve plus one
  check per activation kind, families as sets so ticket 08's measured matching
  rule is one more member — unit (2026-09-24 17:34 ET)
- [x] Matching rules are well formed at registration: family `binding`,
  identifier tests only, `on_no_match` `mint` or `wait` as data, namespaces
  `cik` / `lei` only — unit (2026-09-24 17:34 ET)
- [x] §9.3 deterministic activation on a complete Identifier Contract,
  including its **issuing source datasets** — unit (2026-09-24 17:34 ET)
- [x] Company compatibility is kind equality only (Q9; name similarity is
  ticket 08) — unit (2026-09-24 17:34 ET)
- [x] Merge Stage proposes: an unmatched record whose identifier is on exactly
  one Company joins it; none, and the rule says `mint`, a new Company
  (ADR 0013); `wait` leaves it in the Stage; ambiguous or conflicting is set
  aside — PG16 (2026-09-24 17:34 ET)
- [x] **A Company holds an identifier only through its issuer's own record**
  (Q14: an LEI does not establish a CIK crosswalk because both values exist):
  an LEI through a GLEIF record, a CIK through an SEC record; only the
  issuer's record creates a Company — PG16, found by the spec review (2026-09-24 17:34 ET)
- [x] The lookup uses each record's latest version and resolves a merged
  Company to its survivor; indexed on `cik` and `lei` (migration 035) — PG16
  (2026-09-24 17:34 ET)
- [x] One new Company per identifier value within a batch — PG16 (2026-09-24 17:34 ET)
- [x] Every automatic proposal gets a durable assessment (Q13); migration 035
  lets `record_assessment` accept proposals kept beside the command — PG16,
  populated store (2026-09-24 17:34 ET)
- [x] A redelivered batch returns its first result — PG16 (2026-09-24 17:34 ET)
- [x] A run that proposed a new Company re-checks under the Merge Stage lock
  at apply and re-assesses if the identifier is now held. This **replaces**
  ticket 03's "widen `assessment_snapshot`": the global advisory lock makes an
  in-lock re-check sufficient — PG16 (2026-09-24 17:34 ET)
- [x] Four real Companies: SEC records create Companies, GLEIF records wait —
  PG16 (2026-09-24 17:34 ET)
- [x] Three-axis `/code-review`; fixes above (2026-09-24 17:34 ET)
- [ ] Full suite, PR and CI green
- [ ] **Suspended** identifiers (Q14 lists them among what defers): nothing is
  suspended yet (the suspension table is ticket 03's, unbuilt), so none can
  gain authority; build the check with the table
- [ ] A binding to an existing Company is not re-checked at apply when a
  *different* Company acquires the same identifier meanwhile (only new
  Companies are); the assessment snapshot covers changes to the Company itself
- [ ] A crash between assessment and apply leaves the first assessment
  orphaned; redelivery re-proposes with fresh ids (never mints twice)
- [ ] A new Company's `published_at` is the batch's `as_of`, which the caller
  supplies; a backdated batch could make it the earliest-published survivor
- [ ] Concurrency is proven by a deterministic interleaving, not real threads

Not in this ticket: joining SEC to GLEIF (ticket 08); activating any rule in
`policies/company.json` (ticket 06 approval); mapping SEC's own `lei` key;
the §9.3 suspension counter.
