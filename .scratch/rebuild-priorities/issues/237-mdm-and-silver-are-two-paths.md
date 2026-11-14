# 237: MDM and silver are two paths, so a source extract has at least two splits

Type: task. Status: resolved. Blocked by: none.

## Why

Operator, 2026-11-14: "make it two split one to mdm and one to silver they are naturally two seperate paths
agreed ? yes or no so two step two splits minimum not one", then "update the skills only we will revist all
source extracts again".

Found the same day: folding N-PORT's silver holding rows into its MDM source extract made one reduce hold both
states (7.2 GB on an 8 GB laptop) and made every MDM reader parse rows it skips.

## Parts

- [x] data-onboarding: the fewest steps are one per destination; MDM and silver split into at least two; two
  reduces stay two when one would hold both states (skill edit, this PR; 2026-11-14 18:39 ET)
- [x] refining-rules: a fold stays within its own path (skill edit, this PR; 2026-11-14 18:39 ET)
- [ ] ~~Change the source extracts~~ deferred: the operator will revisit every source extract ("we will revist
  all source extracts again")
- [x] Learning → skill: data-onboarding, "A source extract has the fewest steps that make its records" (2026-11-14 18:39 ET)
