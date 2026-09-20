# Decide how a deterministic binding rule activates

Type: grilling
Status: open
Blocked by: none

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
