# FIGI's check-digit family

Priority: 107, tier 3. Map: [Rebuild priorities](../map.md).

Type: task (code: identifier types and data-profiling's detectors). Status: open. Blocked by: none. Raised by: 105 (Silver rows are checked when they land), 2026-10-17.

## Why

`rules/identifiers/figi.yaml` checks a FIGI's shape only. A FIGI's check digit doubles every second character counted from the left (letters read as 10-35, the digits of each product added), which none of the eight declared families does: on a sample of 51,623 FIGIs from the 2026-10-15 OpenFIGI capture, that rule fails none, and "luhn over letter values" fails 46,384.

A family is named as data-profiling names it (`edgar_warehouse/mdm/clean/identifier_types.py`), so profiling's detectors learn it too, or a FIGI column is never found to carry a check digit.

## Checklist

- [x] GoF consult on `identifier_types.py` and data-profiling's check-digit detectors: leave it. Each family table changed once since it was written (#975, #983), and `test_the_engine_and_profiling_agree_on_each_family` keeps the two in step; a family is one entry in each (2026-10-17 20:23 ET)
- [x] The family, named as profiling names it: `luhn over letter values from the left` (letters 10-35; every second character of the payload, counted from the left, doubled and its digits added; the last character the check digit). Tests on invented values: a FIGI-shaped value passes, a changed check digit is refused as `invalid_figi_checksum`, and Luhn from the right is a different rule; flipping which characters are doubled fails 3 tests (2026-10-17 20:23 ET)
- [x] Profiling detects it (`check_digits` names it on 500 invented FIGI-shaped values); `figi.yaml` version 2 declares it, pinned `040addeb…`, normalizer `normalize_identifier@figi-v2`; the OpenFIGI silver check is `figi_valid` (shape and check digit) (2026-10-17 20:23 ET)
- [x] Measured on the 2026-10-15 capture: all 1,618,040 distinct FIGIs pass the family ("luhn over letter values" fails 1,456,578); the writer's own `figi_valid` check over all 2,184,699 listings flags 0 (2026-10-17 20:23 ET)
- [ ] Three-axis review; PR, CI green, merged on green
- [ ] Learning → skill
