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
- [x] A binding to an existing Company is not re-checked at apply when a
  *different* Company acquires the same identifier meanwhile (only new
  Companies are); the assessment snapshot covers changes to the Company itself
- [x] A crash between assessment and apply leaves the first assessment
  orphaned; redelivery re-proposes with fresh ids (never mints twice)
- [x] A new Company's `published_at` is the batch's `as_of`, which the caller
  supplies; a backdated batch could make it the earliest-published survivor
- [x] Concurrency is proven by a deterministic interleaving, not real threads

## Closing the five open safety items (Claude, 2026-09-26)

One PR, branch `claude/company-mastering-15-cik-rule-safety`; ticket 15's
first checklist item points here. Each item is proved on PostgreSQL 16. The
design changed after the three-axis review (the first version refused a
late batch forever, which broke reordered delivery); what follows is what
was built.

- [x] **One re-check under the Merge Stage lock for every rule proposal**
  (`binding.proposal_is_stale`, replacing `mint_is_stale`): a new Company's
  identifier is still unheld; every identifier a join rested on is still
  held by exactly that Company (a *different* Company acquiring it is
  invisible to the assessment snapshot); no identity of a new Company's
  kind has since been published at or after it. A change to the target
  Company itself (a merge, review) moves the snapshot, which
  `assessment.check` already refuses. PG16: a steward gives the CIK to a
  second Company between assess and apply; the join goes stale and the
  retry reviews it as ambiguous.
- [ ] **Suspended identifier: a technical reading of Q9, for the operator
  to confirm** (ticket 15 asks). A Company the Merge Stage has put in
  review for an identifier or kind conflict gains no record by a rule,
  identifier or name: the record waits in the Stage with a
  `suspended_identifier` review and the rest of the batch commits. Before,
  such a join failed the whole batch. PG16 on a contradiction between two
  records of the CIK's issuing source. **The question underneath, for the
  operator:** the Merge Stage counts every member's identifier claims when
  it decides a Company is in conflict, so a non-issuer's stray value (a
  GLEIF record carrying a CIK) also puts a Company in review. Should a
  claim from a source that does not issue that identifier count at all
  (Q14: "a Company holds an identifier only through its issuer's own
  record")? That is a change to the Merge Stage's conflict count, not made
  here. Q9's "rebuild from remaining trusted evidence" for a CIK
  contradiction has no ticket (ticket 13 covers name-rule links); noted on
  the map.
- [x] **The Merge Stage refuses only a bind or merge into a conflicted
  Company** (found in review). It used to refuse every identity decision in
  a batch that held any conflict, so one contradiction beside an unrelated
  new Company failed both. PG16: the contradicting reading and an unrelated
  new Company commit together; the conflicted Company waits in review.
- [x] **An orphaned assessment is closed when its batch commits**
  (migration 040, 028's `commit_batch` restated whole). The
  `MergeStage.apply` docstring now says what a crash leaves. An orphan whose
  batch never commits stays open; orphans from before 040 are not
  backfilled (that would write run ids that never ran into an immutable
  log; no shared store has been migrated). PG16, including on a store
  populated before 040.
- [x] **A rule's new Company is never published before another of its
  kind** (technical decision, reversible). It is published at the batch's
  `as_of`, or one microsecond after the newest stored identity of its kind,
  whichever is later (`binding.publish_floor`), so a late or backdated
  batch still creates its Company, and "earliest published" means earliest
  committed across batches (within one batch, equal times fall back to the
  entity id, as before). SQL refuses anything else (040). Gaps, recorded: a
  steward's identity states its own time and is not checked, and one dated
  in the future raises the floor for every later rule-created Company of
  its kind. PG16: a late batch; a newer Company committed between assess
  and apply makes the proposal stale; the SQL refusal called directly.
- [x] **Real concurrency:** two threads, separate connections, both
  assessed before either applies: one Company, the other run re-assesses
  and joins it (passed three times in a row).
- [ ] Full suites, three-axis review, PR, CI green.

Not in this ticket: joining SEC to GLEIF (ticket 08); activating any rule in
`policies/company.json` (ticket 06 approval); mapping SEC's own `lei` key;
the §9.3 suspension counter.
