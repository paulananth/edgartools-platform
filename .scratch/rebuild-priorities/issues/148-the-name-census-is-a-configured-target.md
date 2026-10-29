# 148: The Name Frequency census is a configured target

Priority: 148. Map: [Rebuild priorities](../map.md). Opened 2026-10-29 07:50 ET, moved out of ticket 135
(operator, 2026-10-29, agreeing to narrow 135 to the population proof).

Type: task. Status: open. Blocked by: none.

## Question

The Name Frequency census (`edgar-warehouse mdm name-census`) is built in Python (`name_frequency.py`,
`name_census.py`; GLEIF's input checked by `gleif_publication.py`) over configured readings. Codex's
`whole-source-census` workstream left open: "Express complete source census construction in bundled Rules,
with immutable source/context receipts and separate worker verification", then replace its consumers and retire
the Python construction. The Company `mastering` target pins the census by its digest. The result was proven
equal to the original sources to EOF on 2026-10-09 (`whole-source-census`, file sha256 recorded there).

## Parts

- [ ] GoF consult on `name_frequency.py`, `name_census.py` and the combine engine
- [ ] The census as a configured Bookkeeping target (source extract, combine), each step verified by its own
  worker; equal to today's Python census on the whole capture (the 2026-10-09 sha256)
- [ ] Its consumers read the target's output; the Python construction retired, an independent test-only oracle
  kept until the configured one is proven
- [ ] Three-axis review; PR, CI, merge
- [ ] Learning → skill
