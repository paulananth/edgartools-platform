# 141: Company, Person and Fund matched the way Security is

Priority: 141. Map: [Rebuild priorities](../map.md). Opened 2026-10-27 20:36 ET.

Type: grilling. Status: open, not started.
Blocked by: none. Comes from [138](138-one-security-mastering-by-cross-reference.md)'s
follow-up line (operator, 2026-10-25: "Security now, others next tickets": the
table and lookup serve every kind; Company, Person and Fund move in their own
tickets).

## Question

Ticket 138 made a Security's matching identifiers a list read through one
reader, with the lookup index, the Merge Stage and the master read taking any
number of values. A filer's copy of an identifier it does not issue is used
only to look up a master, never to create one (Design 5). For Company, Person
and Fund, which of those rules change what they master today, and which only
need the kind's rules to say so?

## What is known

- The engine names no kind: list identifiers, `reverse` on the Identifier
  Contract, `on_several: merge`, `consolidates`, `on_conflict: first` and the
  lookup-only fallback are rule data any kind may state.
- Company, Person and Fund identifiers state `reverse: 1` (one value per
  master), the limit the engine enforced before 138.
- The mdm-engineering skill says "A filer's copy of an identifier it does not
  issue is lookup only". No Company, Person or Fund rule has been checked
  against it.

## Parts

- [ ] For each kind: list its identifiers, which source issues each, and the
  filers that copy one; measure how many records a copy finds a master by
  (counts only)
- [ ] For each kind: decide whether any identifier needs a list or a reverse
  above 1, with the operator, one question at a time
- [ ] Rules changes, each off until a limited test and the operator's switch-on
- [ ] Tests, three-axis review, PR, CI green, merge
- [ ] Learning → skill
