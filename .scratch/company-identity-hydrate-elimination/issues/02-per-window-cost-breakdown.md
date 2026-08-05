# What is Stage0CompanyIdentity's actual per-window cost breakdown (hydrate vs. merge-publish), and would a minimal/selective hydrate be enough on its own?

Type: research
Status: open

## Question

We know two things cost something on every Stage0CompanyIdentity window
today: (1) `_hydrate_silver_database_from_storage` (full canonical
download+open) and (2) `_publish_silver_database_if_remote` →
`merge_candidate_into_canonical` (shutil.copy2 of canonical + ATTACH +
per-protected-table walk + per-changed-row Python loop, ~21 tables). We
don't yet know their relative weight, or whether fixing only #1 would
leave #2 as a comparable bottleneck across load_history's 53 windows.

Investigate, using real evidence (code + CloudWatch/logs from the live
runs already in this repo's history — the failed execution `load-history-
1785942443` and its retries against window offset=0/limit=500 are a real
data point, plus the earlier `ReduceIdentityRefresh` measurement of ~188s
for 4 candidates against a ~1021.8MB canonical referenced in this map's
Notes):

1. Read `_publish_silver_database_if_remote`'s skip-if-unchanged fingerprint
   check (`compute_silver_fingerprint`, release-readiness ticket 79). For
   a company-identity window that only touches a handful of small tables
   (`sec_company`, `sec_company_filing`, `sec_company_address`, `sec_
   company_former_name`), would most windows actually hit this no-op skip
   in practice, or does something about company-identity's write pattern
   (e.g. touching `sec_company_filing` on every window) defeat it?
2. Characterize what `merge_candidate_into_canonical`
   (`edgar_warehouse/silver_protection.py`) actually costs as a function of
   canonical DB size vs. candidate/delta size — is the ~21-table
   `information_schema` walk + per-table comparison cost dominated by
   canonical's total size (in which case a smaller candidate doesn't help
   much) or by how much actually changed (in which case avoiding needless
   touches to unrelated tables matters)?
3. Would restricting the *hydrate* step to only the tables company-identity
   mode actually reads/writes (skip `sec_thirteenf_holding`, `sec_
   financial_fact`, etc. via selective DuckDB ATTACH + targeted table copy
   instead of a full file download) meaningfully reduce peak memory on its
   own, holding the current per-window publish step constant? Would it
   also reduce publish cost (a smaller local candidate DB), or is publish
   cost driven by canonical's side of the merge regardless of candidate
   size?
4. Given ticket 01's findings on the delta-then-reduce alternative, produce
   a rough order-of-magnitude comparison: selective-hydrate-keep-per-
   window-publish vs. delta-then-reduce, for a 53-window load_history run
   against current canonical size. Doesn't need to be precise — needs to
   be enough to tell which family of fix is worth pursuing first.

Report findings with a clear recommendation on whether minimal-hydrate
alone is sufficient, or whether the per-window publish cost also needs to
change.
