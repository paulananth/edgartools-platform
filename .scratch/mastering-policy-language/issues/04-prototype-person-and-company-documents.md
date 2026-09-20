# Prototype a Person and a Company policy document

Type: prototype
Status: resolved
Blocked by: 03

## Question

Make the language concrete enough to react to. Write two policy
documents, in full, in the shape decided so far:

- **Person** — expressing rule C-J's five steps (classification, carried
  by each source's dataset contract per research 01), Tiers A–D from
  ticket 02, the 99% bar, the activation entry for C-J's `person` verdict
  only (research 02), and survivorship + projection for the Person fields
  ticket 04 of that map settles.
- **Company** — expressing the GLEIF consumer contract's binding rules
  (Adjudicated Seed Links, deterministic crosswalks, one active binding
  per side), the 99.9% bar, no activated rules, and survivorship with
  SEC authoritative / GLEIF additive.

Both must compose into the one body the Merge Stage pins, and must use
only the primitives ticket 03 fixes. The prototype answers, by being
written: is the language expressive enough for what we have already
decided, and is it readable by an operator who must maintain it?

Record what the exercise breaks. Anything the documents cannot say
without a new primitive or a new section is a finding for ticket 03 or
the spec, not a silent addition.

## Answer

Resolved 2026-09-20. **The language holds.** Both documents were written in the
twelve-primitive vocabulary and a throwaway interpreter reading them reproduces
research 18's measured result exactly: **person 841/841, entity 353/353, 26
deferred** over the 1,220-row labeled sample, and 1.2% deferral over the whole
5,743-row corpus. Rule C-J's `person` verdict comes back `automatic`; its
`entity_undetermined` verdict comes back Steward-review — one rule, two
verdicts, exactly Person ticket 03's release gates 1 and 2.

Artifacts (`prototype/`, throwaway, not production):

- `policy-person.json` — C-J's five steps with the 125 legal-form words, the
  ambiguous and suffix lists and the six structural field paths as
  *parameters*; Tiers A–D as binding rules; the 99% bar; one activation entry,
  for `C-J`/`2026-09-20`/`person` only; survivorship and projection.
- `policy-company.json` — CIK Tier A, Adjudicated Seed Link and deterministic
  crosswalk binding rules, the 99.9% bar, **no** activated rules, SEC-
  authoritative / GLEIF-additive survivorship.
- `interpret.mjs` — the pure interpreter: primitive registry keyed
  `name@version`, the registration-time static checks, `classify`, `bindings`.
  This is the part worth lifting if the spec is accepted.
- `run-check.mjs` — the verdict run (`node run-check.mjs`).
- `demo.html` — self-contained page; open by double-click. Six guided cases
  (officer, fund, `MALONE JOHN C`, `Trust Jane`, an operating company, never
  captured) plus free play, showing which step fired and why.
  Rebuild with `node build-demo.mjs` after editing the interpreter or document.

The registration checks refuse all six abuse cases: a rule edited after its
proof, a bar raised above the proof, a proof measured at a different confidence
coverage, a fabricated lower bound, activating a verdict the rule cannot emit,
and a binding rule that would decide on name similarity alone.

### What the exercise broke — findings for the spec

1. **A deterministic binding rule has no home in the activation model.** Person
   Tier A (bind by `owner_cik`) fires but reports *Steward review*, because the
   document carries no proof block for it — research 02's model requires a
   measured precision for every automatic rule, while Person ticket 02 calls
   Tier A automatic by construction. The spec must either require a
   verification sample for deterministic rules too, or declare a second
   activation kind whose evidence is the identifier's semantics plus a
   cardinality check, not a precision number. **This is the largest open
   question the prototype surfaced.**
2. **The field-alias map has no declared home.** `run-check.mjs`'s `ALIAS`
   (document path → source column) is exactly the dataset contract's adapter
   block research 01 pointed at, and nothing in the map has specified it. Until
   it is declared, a policy document cannot be read against a real source.
3. **An `otherwise` step needs a name.** C-J's step 4 is expressed as an empty
   `when` list, which reads as "always true". Legible in code, easy to
   mis-edit by hand; the spec should give the catch-all its own keyword.
4. **`&` must be written `AND` in a declared list.** EDGAR conformed names
   normalize `&` to ` AND `, so an operator adding "Smith & Co" to the token
   list by typing `&` silently gets nothing. A sharp edge worth a validation
   rule, not a footnote.
5. **Survivorship could not be exercised.** It needs a populated identity
   store, so the prototype validates classification and binding only. The
   Person projection block is a placeholder (Person map ticket 04 is
   unresolved), and the Company address field group cites accepted policy that
   `survivorship.py` does not implement — already flagged to Codex by research 03.
6. **The vocabulary held with nothing added.** `token_match` alone covers step
   2 (unambiguous token), step 2-guard (exactly one token) and step 3
   (negated), which is the minimality claim doing real work.
