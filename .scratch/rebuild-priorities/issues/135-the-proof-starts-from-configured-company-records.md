# 135: The recreation proof starts from configured Company records

Priority: 135, tier 2, the recreation proof. Map: [Rebuild priorities](../map.md).
Opened 2026-10-22 from the map review ("review all existing ticket and provide a
way to complete the project").

Type: task. Status: open; waits for the operator's ruling on who builds it.
Blocked by: nothing on this map (#1121 and #1142 merged).

## Question

[32: the recreation proof](32-profiling-08-recreation-proof.md) defers its
baseline and its cold-agent run to one unchecked item of the
`sec-configured-fields` workstream
(`.planning/workstreams/sec-configured-fields/TICKET.md`, line 9): "retire
Company preparation/census/provenance and GLEIF release/semantic consumers;
prove whole-source census and installed 6,414 Company / 3,052 CIK+LEI
population/recovery". Mastering starts from SEC Company records (GLEIF alone
binds nothing), and the Company input is still the retained Company
preparation that item retires; a baseline taken today would measure a path
about to be removed. Neither #1121 nor #1142 ticked it (checked 2026-10-22
21:11 ET).

What is left before 32's baseline can run:
- the Company records come from the configured source extract, combine and
  `mdm.prepare` chain, never the retained preparation;
- the census and provenance consumers read the configured outputs;
- the installed population proof repeats: 6,414 Companies and 3,052 CIK+LEI
  bindings from an empty store, a second pass changing nothing.

The item sits in another runtime's workstream file. Nothing is owned by Codex
(operator, 2026-10-16), and the overlap rule still applies: take it over only
on the operator's ruling, then build on Codex's merged work, never beside an
open branch.

## Checklist

- [ ] Operator's ruling: Claude takes the item over, or it waits for Codex
- [ ] The item's remaining parts listed here from the workstream file, each with its evidence
- [ ] Built, reviewed (Standards, Spec, GoF), PR, CI green, merged
- [ ] 32's two deferred parts re-opened on this ticket's merge
- [ ] Learning → skill
