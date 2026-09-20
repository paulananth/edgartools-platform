# Decide how a deterministic binding rule activates

Type: grilling
Status: resolved
Blocked by: 07

## Question

The prototype surfaced this by breaking on it. Person Tier A — "bind by
`owner_cik`; one identifier resolves to exactly one Person" — fires
correctly but cannot run automatically, because research 02's activation
model requires a **measured precision proof** for every automatic rule,
and a deterministic identifier rule has no precision to measure. Person
ticket 02 nonetheless calls Tier A automatic by construction.

Both cannot be true. Which is it?

- (a) **One activation kind.** Deterministic rules carry a proof too: a
  verification sample (n identifiers checked, n correct) measured the same
  way, so the arithmetic check is unchanged. Cost: a sampling exercise per
  identifier namespace before any deterministic rule runs alone.
- (b) **Two activation kinds.** A `deterministic` kind whose evidence is
  not a precision number but a declared identifier contract — the
  namespace's semantics, the authority that issues it, the cardinality
  guarantee (`identifier_cardinality`), and the evidence that the
  guarantee was verified on the corpus. The Merge Stage checks a different
  predicate for this kind.
- (c) Something else: e.g. deterministic rules are not "rules" at all but
  part of the dataset contract's identifier declaration, and never appear
  in `automatic_rules`.

Consider what each does to: research 16's finding that a CRD `OwnerID` is
**not** unique per natural person (so its cardinality guarantee is false
and duplicates must collapse onto one Person); Clean MDM's accepted Q11
and Q16 wording, which speaks of precision only; and replay, which must
reproduce the same decision under the pinned body.

The answer is a section of the spec (ticket 05), which is blocked on it.

## Comments

- 2026-09-20, Q1 settled (operator: "agreed"): **(b) — two activation
  kinds, with teeth.** A `deterministic` rule activates on an identifier
  contract (issuing authority, namespace, the *direction* of the
  cardinality claim) plus a measured verification that the claim holds on
  the corpus. Clean MDM's own hook: "Exclusivity is policy-specific"
  (`domain-model.md:46-48`).
- Q2 (what happens when the claim is later violated: defer the record /
  deactivate the rule / defer and count against a declared tolerance) is
  held until research 07 measures the `owner_cik` violation rate and runs
  all three behaviours on real data. Operator chose measurement over
  argument.

## Answer

Resolved 2026-09-20 (operator: "agreed" on Q1 and Q2). Written for the
implementer; the spec (ticket 05) carries this as its "deterministic
activation" section.

### Decision

**Two activation kinds.** Besides the `measured` kind (research 02: a
precision proof per `(rule_id, rule_version, verdict)`), the policy
document admits a **`deterministic`** kind whose evidence is an
**identifier contract** plus a **measured verification** of that contract
on the corpus. When the contract is later violated at runtime, the rule
**defers the record and counts** (Q2 option c), deactivating itself only
when distinct violating items cross a declared line after a declared
warm-up.

### The identifier contract (declared per namespace, in the kind document)

Clean MDM's own hook: "An identifier has authority, namespace, normalized
value, scope/jurisdiction, valid interval, and source assertion.
**Exclusivity is policy-specific.**" (`docs/specs/clean-mdm/domain-model.md:46-48`).
The contract is where exclusivity is declared:

| Field | Meaning | `sec.cik` (Person) | `crd.individual` (Person) |
| --- | --- | --- | --- |
| `authority` | who issues the value | SEC/EDGAR | FINRA/IARD |
| `namespace` | the value space | `sec.cik` | `crd.individual` |
| `normalizer` | `name@version` | `normalize_identifier@sec-cik-v1` | `normalize_identifier@crd-v1` |
| `claim.forward` | one value → at most N identities | **1** | **1** |
| `claim.reverse` | one identity → at most N values | unbounded (cross-reference ids, ticket 02) | unbounded — duplicates measured at ~12/10k (research 16) |
| `compatibility` | the second handle the runtime veto compares, its predicate and version, **and the field** | `owner_name`, `name_compatible@lenient-v1` | `name`, same |
| `verification` | the measurement that earned activation | 0/72,981 decisions, Wilson UB 0.53/10k; reverse 0/16,677 same-issuer pairs; corpus hash; who/when | research 16 figures; **forward claim only** |

Key facts behind `sec.cik`'s claim, for the record: EDGAR discards any
filer-supplied `rptOwnerName` and inserts the CIK's registered name
(Ownership XML Technical Specification v5.1 §4.3.2), so a name difference
on one CIK is a registered-account event, not a different person; all 42
two-name CIKs in 104,970 rows were read by hand — variants, name changes,
nicknames, typos, entity renames. `crd.individual` cannot make the reverse
claim; the two Tier A rules differ in contract, not just in namespace.

### The Merge Stage predicate for a `deterministic` activation

Fail closed, pure over the body, alongside research 02's `qualified()`:

1. the entry names `(rule_id, rule_version, verdict)`, and the rule's every
   `identifier_match` names a namespace whose contract is declared;
2. the contract declares `claim.forward`, `compatibility` (predicate,
   version, field) and `verification` with a corpus hash;
3. every primitive named — normalizer, compatibility predicate — resolves
   to a registered `name@version`, else refused;
4. the `tolerance` block is present and complete (below).

### Runtime behaviour when the claim is violated (Q2 = c, tuned)

Research 07 ran (a), (b), (c) over 72,981 real person decisions plus a
synthetic bulk failure. (b) deactivated at decision 3,107 on a middle
initial and sent 96% of the corpus to the Steward — **out**. (a) is
sufficient on the measured data but **silently bound 784 wrong rows and
minted 291 bogus Persons** under the injected failure, because an unbound
wrong id never collides. (c), tuned, **never trips on real data** and
stopped the injected failure within 8–48 decisions. So:

- **Detect**: `identifier_cardinality@1` resolves the incoming id to an
  existing identity and compares the incoming `compatibility.field` with
  the names already on that identity using the declared predicate.
  A "materially new" name is the candidate violation. This is a heuristic
  inside a deterministic rule and **must be declared and versioned** — the
  prototype had to reach for `owner_name` as a literal because the rule's
  `args` named no field.
- **Defer**: the violating record goes to the Steward as a deferred record.
  The rule keeps running for every other record.
- **Count**: distinct `(identifier, incoming normalized name)` **items**,
  not records — one prolific filer with one typo'd registered name is
  otherwise a burst (27 records for one typo in the corpus).
- **Line**: declared in the contract's `tolerance` block:
  `{"unit": "items", "warm_up_decisions": 10000, "max_per_10k": 5,
  "predicate": "name_compatible@lenient-v1"}`. These are the measured
  values that never trip on real data and still catch a bulk failure;
  they are **parameters pinned by the digest**, changed only by a new
  document version.
- **Deactivate**: when the rate crosses the line after warm-up, the rule's
  automatic verdict is withdrawn for the rest of the batch and thereafter;
  every decision it would have made goes to review until a new document
  with a fresh verification is registered. Recorded as evidence against
  the contract, in the batch's commit evidence.
- **Steward resolution must record the alias.** The queue under this
  model is alias confirmations, not identity decisions; without recording
  the alias the same item recurs on every later filing.
- **Reverse-direction hits** (a Person would acquire a second value) are
  reported as consolidation candidates, never vetoed — a Person holds any
  number of cross-reference ids (ticket 02).

### Limits stated honestly

- The runtime can see only **name-mismatch alarms**, not true violations;
  every alarm on real data was false. A different person with a
  compatible name is invisible to any runtime check — the contract's
  verification, not the runtime, is what guards against that.
- The tolerance values are tuned on one failure shape (bulk wrong id);
  the price of a real bulk failure in production, which is what would
  justify or retire the knobs, is unmeasured.
- 5,607 of 19,735 legacy owner CIKs have no captured `submissions.json`
  (C-J defers them, step 0) and 6 labelled items stayed uncertain.

### Evidence

[research/07](../research/07-owner-cik-cardinality-and-deterministic-binding.md)
with `07-measure.py`, `07-cardinality.json`, `07-labelled-sample.jsonl`,
`07-run-binding.mjs`, `07-binding-results.json`, and the runtime
prototype `prototype/interpret-binding.mjs` (a copy; `interpret.mjs` is
untouched and still reproduces research 18).
