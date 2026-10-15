# The engine tells whether two lists share a value

Priority: 93, tier 1. Map: [Rebuild priorities](../map.md).

Type: task (engine). Status: in progress (branch `claude/list-overlap`). Unblocks: 79 part 1 (the N-PORT Security's ISIN, decided with OpenFIGI) and 80 (OpenFIGI).

## Why

Operator, 2026-10-15, choosing the ISIN rule for the N-PORT Security: "Use FIGI to add pairs too". A CUSIP Security carries an ISIN when:
1. the quarter's filings pair them one to one and OpenFIGI says they are the same security (346,535); or
2. the ISIN was filed with several CUSIPs and OpenFIGI names exactly one of them (4,338); or
3. an ISIN-only holding's ISIN is tied by OpenFIGI to one N-PORT CUSIP (5,394; all already pairs of case 1).

Otherwise the CUSIP carries none, and a CUSIP offered two ISINs, or an ISIN offered to two CUSIPs, is refused and counted (`.scratch/onboarding/sec.nport/security-figi-attachment.json`: 350,873 CUSIP Securities with an ISIN).

"The same security" means the CUSIP's answer and the ISIN's answer share a listing or composite FIGI. Share-class FIGIs, which span countries, change no count here, and are left out. Each answer is a set of FIGIs (about 6 listings per equity; a bond has no composite).

The reading, reduction and combine group, count, join and choose. They cannot tell whether two lists share a value, so they cannot decide case 1 or 2.

## What changes

- A generic expression, `overlap: {left: <expression>, right: <expression>}`: true when two lists of text share a value, false when they share none, null when either is null. Bounded by the existing list and text limits. It names no source or kind.
- Configuration then does the rest (data-onboarding, configuration only):
  - an OpenFIGI reading of the capture (ticket 80);
  - the FIGIs of each CUSIP and ISIN, reduced;
  - joined onto each filed pair in combine, then a reading over the combined rows applies `overlap` (combine and reduction never evaluate expressions; only a reading does);
  - cases 2 and 3 counted by reduction;
  - the CUSIP's one ISIN chosen in combine with `mode: one`.
- Re-run only the stages after the change (the holdings are not read again), then the one Proving Run.

## Checklist

- [x] The operator's word to code it: "Yes, code 93 (Recommended)" (2026-10-15)
- [x] GoF consult before code: add `overlap` beside `equal` (no table of primitives: 23 differing arms, one file); test a nested expression inside it, since `expression_children` must list it (2026-10-15 14:15 ET)
- [x] `overlap` in Rust beside `equal` (PRIMITIVES, children, validate, eval); `tests/overlap.rs`: shared, none, empty, null, missing, non-text refused, a nested `context` read, arguments refused; all 31 crate test binaries pass (2026-10-15 14:15 ET)
- [x] READING.md: `overlap`, after the assertions section (2026-10-15 14:18 ET)
- [x] Three-axis review (Standards, Spec, GoF): GoF leave it; fixed the doc's place, one refusal for any non-text list (a null item included, tested), and the ticket now says a reading over the combined rows applies `overlap`. Rust: 31 crate test binaries pass; Python: 336 engine, stream, lookup and architecture tests pass (2026-10-15 14:18 ET)
- [ ] PR, CI green, merge on the operator's word
- [x] Learning → skill: data-platform READING.md, `overlap` (compare two sets in a reading; combine and reduction never evaluate expressions) (2026-10-15 14:18 ET)
