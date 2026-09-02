# Decide the S3 Deletion Boundary

Type: grilling
Status: resolved
Blocked by: 06

## Question

Which artifact classes may become deletion candidates after their settled
retention window, and should the tool stop at a hash-bound dry-run manifest or
also gain a separately authorized apply command?

The recommended boundary is: expire only explicitly classified derived,
staging, noncurrent, and disposable run artifacts; retain immutable Bronze SEC
source evidence indefinitely while transitioning eligible old objects to a
cheaper storage class; and generate a reviewed deletion manifest without an
automatic apply path.

## Answer

Resolved 2026-09-02. The user explicitly rejected retain/transition as the
terminal policy for expired Bronze and directed that S3 objects be deleted
according to the years in scope for each artifact.

Implementation contract:

- Use canonical consumer windows as policy input: 13F 3 years, proxy 5 years,
  ownership Forms 3/4/5 2 years, Item 5.02 8-K 2 years, and ADV current plus 2
  years. Report current runtime drift rather than silently adopting narrower
  runtime defaults.
- Build an Accession Retention Authority because the existing S3 key does not
  encode form/item type. Use the maximum applicable consumer cutoff.
- Select the complete index/document/text bundle and exact current/noncurrent
  VersionIds. Never delete a partial, unmatched, unexpired, or concurrently
  changed bundle.
- Bind apply to the reviewed plan hash, revalidate identity/version state, keep
  pre/post evidence, and fail closed on drift.
- Existing day-based ephemeral rules remain day-based; unsettled non-filing
  classes remain unmatched until a year/day policy is supplied.
