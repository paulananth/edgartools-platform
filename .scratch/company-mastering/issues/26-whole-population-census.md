# Count every SEC filer in one Name Census

Type: task
Status: in review (Claude, branch `claude/company-mastering-26-whole-population-census`)
Blocked by: nothing
Blocks: the Proving Run of the completion gate (option A)

## Operator rulings

- "i want to complete company master", option **A** (2026-09-29): the
  Proving Run on real pinned data with the name rules on, then the operator
  approves the final policy fingerprint.
- Asked "Build the whole-population census this way (one-time ~2 hours of
  machine time, plus the preparer change), then run the Proving Run?":
  **"yes"** (2026-09-29).

## Why

Both name matching rules need the name to be unique across all SEC filers
and all of GLEIF. A Name Census counted one SEC capture only, and one
capture holds at most 1,000 filers (`prepare_company_bundle` caps
`--limit`). A census of 1,000 filers would call a name unique that another
of the 76,230 filers also uses, so the rules would merge on a false
uniqueness.

## Done

- `write_name_census` takes a list of landing manifests and counts the
  filers of every capture, with one pass over the GLEIF Golden Copy.
- A filer (CIK) in two captures is refused. One capture is not checked, so
  it behaves exactly as before.
- A census of one capture keeps today's `sec` shape, so existing censuses
  and their digests are unchanged. A census of several captures records
  `{"captures": [...], "filers": n}`.
- A cascade pass still needs a census of one capture; several are refused.
- `prepare_company_bundle` accepts a census if any capture it counted is
  this Company capture (same run id and member hash).
- `mdm name-census --landing-manifest` may be given more than once.
- Test: `test_a_census_counts_every_capture_and_each_capture_uses_it`
  (two captures, the same name under two CIKs, the preparer accepts the
  census for either capture, a repeated capture is refused).

## Review (three axes)

- Standards: no violations. Fixed: the CLI list is named
  `landing_manifests`; the census's SEC block is read as `sec`; an empty
  list raises `Conflict` like every other refusal; the duplicate check runs
  only across captures, so a one-capture census is unchanged.
- Spec: fixed: the test now prepares the second capture from the same
  census too. Kept as is: nothing proves the captures are the whole SEC
  population; the Proving Run's report states the count (76,230) and the
  77 manifests. The Bookkeeping path (`bookkeeping/clean/company.py`) still
  checks a census pinned to one capture; the Proving Run uses
  `mdm name-census` and `mdm prepare-clean-company`, not that path.
- GoF: leave it. The two shapes of the SEC block are kept on purpose so
  existing census digests do not change.

## Next

- Land all 76,230 filers from the local bronze copy (77 captures of at most
  1,000, network blocked), build one census over them, and run the Proving
  Run.
