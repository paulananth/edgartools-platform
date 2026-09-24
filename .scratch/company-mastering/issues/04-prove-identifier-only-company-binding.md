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

- [ ] Reshape `activation._check_activation` into a shared resolve plus one
  check per activation kind (GoF, ticket 03 review), no behaviour change
- [ ] Binding rules are well formed at registration: family `binding`,
  identifier primitives only, `on_no_match` of `mint` or `wait` as data on the
  rule, namespaces `cik` / `lei` only
- [ ] §9.3 deterministic activation: every namespace a rule names has a
  complete Identifier Contract (authority, normalizer, forward claim,
  compatibility, verification, tolerance)
- [ ] Company compatibility is **kind equality only**: Q9 says a name change
  never revokes a binding, and a name-similarity check is fuzzy matching
  (ticket 08)
- [ ] Merge Stage proposes automatic bindings: an unbound record whose
  identifier resolves to exactly one Company binds to it; none, and the rule
  says `mint`, a new Company is created inside the Merge Stage (ADR 0013);
  `wait` leaves it in the Stage; ambiguous or conflicting defers
- [ ] One new Company per identifier value within a batch (ticket 03,
  decision 3)
- [ ] Every automatic proposal gets a durable assessment (Q13), including a
  load batch that carries only records
- [ ] A redelivered batch still returns its first result: the generated
  proposals sit outside the batch hash
- [ ] Concurrent runs cannot mint two Companies for one identifier: re-check
  under the Merge Stage lock at apply, stale on a change, re-assess. Replaces
  ticket 03's "widen `assessment_snapshot`"
- [ ] One bulk identifier lookup per batch, no per-record query
- [ ] PG16: lost acknowledgement, concurrent same CIK, reordered input, GLEIF
  waits with no master, a second dataset with the same CIK binds, the four
  Companies mint from SEC
- [ ] Full suite, three-axis `/code-review`, PR and CI green

Not in this ticket: joining SEC to GLEIF (ticket 08); activating any rule in
`policies/company.json` (ticket 06 approval); mapping SEC's own `lei` key;
the suspension counter (§9.3 tolerance is declared, not yet counted).
