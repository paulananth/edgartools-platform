# Profile any source

Type: task
Status: open
Blocked by: 03

## Outcome

`rules profile <files>` works on any format (json, jsonl, xml, csv, zip) with
bounded memory. It reports:
- paths, types, fill rate, distinct counts and samples;
- candidate keys and repeated groups;
- entity hints;
- dates and addresses;
- cross-references;
- identifier candidates: check digits for LEI, CUSIP and ISIN, shape only for
  CIK, CRD, EIN and tickers.

The output is JSON plus a plain summary.

## Checklist (times ET)

- [ ] `/gof-refactor-reviewer` before code.
- [ ] Profiler reusing the engine readers.
- [ ] Tests:
  - valid and invalid check digits;
  - one fixture per format;
  - a memory bound on a large file.
- [ ] Three-axis `/code-review`, then PR and CI.
