# Does daily_incremental's delta-then-reduce Identity Refresh pattern generalize to load_history's Stage0CompanyIdentity?

Type: research
Status: open

## Question

`daily_incremental`'s bounded Identity Refresh (`--cik-list` +
`--identity-refresh-run-id`) avoids `load_history`'s Stage0CompanyIdentity
problem (full-canonical hydrate + full-canonical merge-publish per window)
by using a different architecture entirely: each batch calls
`persist_batch_outcome` (`edgar_warehouse/application/identity_refresh_
publication.py`) to write an immutable CIK-scoped delta artifact instead of
merging into canonical directly, and a single later `reduce_identity_
refresh` call folds all deltas into canonical once.

Investigate, reading the actual code (not just the docstrings/comments):

1. Trace `persist_batch_outcome` and `reduce_identity_refresh` end to end.
   What does a delta artifact actually contain? What does the reduce step
   actually do to merge deltas into canonical — is it the same `merge_
   candidate_into_canonical` cost, just paid once instead of N times, or
   something cheaper?
2. What does `reduce_identity_refresh` require to have already happened
   before it runs (e.g. does it need ALL batches to have completed first,
   like a barrier)? How is that barrier currently implemented/orchestrated
   for `daily_incremental`?
3. `load_history`'s Stage0CompanyIdentity has a hard sequencing invariant:
   Stage1Parallel (ownership/ADV work) must not start until company data
   has actually landed in canonical, because `IS_INSIDER` derivation skips
   unresolved issuers. If Stage0CompanyIdentity switched to delta-then-
   reduce, would inserting a single reduce step between all windows
   completing and Stage1Parallel starting preserve that invariant exactly,
   or does something about the current per-window-publish shape provide a
   guarantee delta-then-reduce would lose (e.g. per-window failure
   isolation, partial progress visibility)?
4. Are there any other differences between load_history's Stage0
   (`ToleratedFailurePercentage=0`, strict, no Catch-and-proceed) and
   daily_incremental's bounded Identity Refresh that would make reusing
   this pattern unsafe or need adaptation — e.g. does `persist_batch_
   outcome`/`reduce_identity_refresh` have any built-in tolerance for
   partial/missing batches that would conflict with Stage0's strictness?
5. Does `reduce_identity_refresh` itself carry a `merge_candidate_into_
   canonical`-shaped cost that would scale with load_history's 53-window
   scale the same way (i.e. does batching 53 windows' worth of company
   data into ONE reduce still touch all ~21 protected tables once, or does
   the delta's small size make the per-protected-table walk itself cheaper
   than what Stage0 pays today)?

Report a clear verdict: does this pattern generalize to load_history's
Stage0CompanyIdentity, with what adaptation if any, or does it not fit and
why not.
