# FIGI's check-digit family

Priority: 107, tier 3. Map: [Rebuild priorities](../map.md).

Type: task (code: identifier types and data-profiling's detectors). Status: open. Blocked by: none. Raised by: 105 (Silver rows are checked when they land), 2026-10-17.

## Why

`rules/identifiers/figi.yaml` checks a FIGI's shape only. A FIGI's check digit doubles every second character counted from the left (letters read as 10-35, the digits of each product added), which none of the eight declared families does: on a sample of 51,623 FIGIs from the 2026-10-15 OpenFIGI capture, that rule fails none, and "luhn over letter values" fails 46,384.

A family is named as data-profiling names it (`edgar_warehouse/mdm/clean/identifier_types.py`), so profiling's detectors learn it too, or a FIGI column is never found to carry a check digit.

## Checklist

- [ ] GoF consult on `identifier_types.py` and data-profiling's check-digit detectors
- [ ] The family, named as profiling names it, with a test on invented values
- [ ] Profiling detects it; `figi.yaml` version 2 declares it (a new version: its normalizer gets a new name)
- [ ] Measured on the capture with the writer's own checks: 0 failures expected
- [ ] Three-axis review; PR, CI green, merged on green
- [ ] Learning → skill
