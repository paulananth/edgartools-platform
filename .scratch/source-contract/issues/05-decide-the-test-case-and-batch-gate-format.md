# Decide the test-case and batch-gate format

Type: grilling
Status: resolved (2026-09-21)
Blocked by: 01, 03

## Question

Decide how the `tests` section is written:

- parse cases: fixture reference, expected silver rows, how partial
  expectations and ordering work;
- mapping cases: expected assertions (kind, identifiers, fields,
  evidence-only fields);
- mastering cases: declared existing identities, expected bind / create /
  defer outcome and surviving fields;
- the batch gate: which metrics (coverage, deferral rate, row counts …),
  thresholds, and how a result is recorded as proof for go-live;
- the failure output format (check 9).

Carried in from ticket 04: **custom checks** (Q6 allowed them per source) —
their shape and rules; and the gate on custom-step `reject(reason)` counts.

## Decisions in progress

- **Q1 Expectations (2026-09-21, agreed):** **named cases are required** —
  each names what it proves, points at a fixture in the source folder, and
  lists only the columns that matter; every known trap gets one. **A
  snapshot is optional**, a regression net only (e.g. Form 3/4/5 against
  `ownership.py`). A changed snapshot is re-recorded only by a command that
  prints the row-level diff, and the Proving Run records who accepted it —
  an agent cannot silently re-record to pass.
- **Q2 Case shape (2026-09-21, agreed):** one case, three optional parts —
  `expect.silver` (parse), `expect.mdm` (assertions: kind, identifiers,
  fields, evidence-only), `expect.merge` (outcomes). Existing identities are
  `given.identities` seed fixtures run through the same contract, never
  inserted rows, and are named by the case (`jane`), never by generated ids.
  Merge outcomes: `bound` (to a named identity), `new`, `binding_required`,
  `deferred` (reason), `quarantined`, field `winner`. Until Codex's
  automatic-rule test mode exists, `bound` checks a declared binding; the
  runner reports which it checked. `source prove` runs parse and mapping
  cases first and starts Postgres only for cases with `merge:`.
- **Q3 Checks (2026-09-21, agreed):** **built-in checks** first — a fixed
  engine list (`not_null`, `unique`, `in_set`, `pattern` with a literal
  regex, `row_count`); a **custom check** is the third custom shape
  (`@check_step`, named inputs → `None` or a problem message) under the same
  six rules. Every check reports **violations with the row key and a
  message**, never a bare true/false. Checks run in each test case (any
  violation fails it) and in the batch gate (against a limit, Q4).
- **Q4 Batch gate (2026-09-21, agreed):** declared in the contract's
  `gate:` — a batch (`family`, `select: all` or a **seeded** sample) and
  limits on `rejected`, `deferred`, `rows`, each check, and an optional
  snapshot. **Default limit is zero**; any looser limit needs a `why:`,
  which is stored in the proof (comments never reach the database). The
  batch is pinned by the hash of its artifact list. The proof stored with
  the version in the Rules Database: contract, custom-code and fixture
  digests, engine version, batch hash, each metric with its limit and
  `why`, pass/fail, time, runner. The gate proves the source contract only;
  a binding rule still needs the policy language's precision proof and a
  Rule Activation Approval.
- **Q5 Failure output (2026-09-21, agreed):** one format, two renderings.
  Every failure starts `file:line` (for a Rules Database version, its line
  in the `source export` YAML), names the case or rule, shows a per-column
  expected/actual diff for the listed columns only, gives the data location
  (RFC 6901) and fixture, and caps violation samples (`--all`). The summary
  states the version's resulting state. Exit codes: 0 proven, 1 test/check/
  gate failed, 2 contract invalid, 3 engine or custom-code bug.
  **Operator note: most testing and validation will be done by the agent**,
  so `--json` (one structured record per failure: file, line, contract
  pointer, rule or case, expected, actual, fixture and data location,
  violation count, limit, sample keys) is the primary interface; the
  terminal rendering is for human review of the same facts.

## Answer

A contract's `tests:` are **named cases** (required; intent-first, listed
columns only) plus an optional **snapshot** re-recorded only through a diff
that the Proving Run attributes. One case shape covers parse
(`expect.silver`), mapping (`expect.mdm`) and mastering (`expect.merge`,
with `given.identities` seeded through the same contract and named by the
case). `checks:` are built-ins or a `@check_step` custom check, all
reporting violations with row keys. The `gate:` runs a pinned (seeded)
batch against limits that default to zero and need a `why:` otherwise, and
stores the proof with the version in the Rules Database. Failures print
`file:line`-first with per-column diffs and distinct exit codes, and emit
the same facts as `--json` — the primary interface, since the agent does
most of the testing and validation.
