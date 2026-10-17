# One test helper runs the read, combine and prepare chain

Priority: 106, tier 4, housekeeping. Map: [Rebuild priorities](../map.md).

Type: task (tests only). Status: open. Blocked by: none. Raised by: 80 (Onboard OpenFIGI with the skills), GoF finding 1 of its first review, 2026-10-17.

## Why

Four integration tests each carry their own copy of the steps that run configured rules over invented files: put a manifest, run `source_read` and verify it, run `source_combine` and verify it, run `mdm_prepare` and verify it, then normalize the prepared lines:
- `tests/integration/test_adv_custodian_link.py`
- `tests/integration/test_nport_link_start.py`
- `tests/integration/test_nport_isin_link.py`
- `tests/integration/test_openfigi_security.py`

The copy was repeated by #1022, #1025, #1030 and #1046, so the next onboarding test will copy it a fifth time, and a change to a worker's task shape is a change in four places.

## Checklist

- [ ] GoF consult on the four copies
- [ ] `tests/support/source_chain.py`: read, combine, prepare and normalize, each verified, from a rules folder and an artifact store
- [ ] The four tests use it; each still passes, and their assertions are unchanged
- [ ] Three-axis review (Standards, Spec, GoF); PR, CI green, merged on green
- [ ] Learning → skill
