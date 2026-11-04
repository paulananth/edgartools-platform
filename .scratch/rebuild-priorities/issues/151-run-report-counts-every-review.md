# 151: The run report counts every open review

Priority: 151. Map: [Rebuild priorities](../map.md). Opened 2026-11-01 11:03 ET, from [ticket 32](32-profiling-08-recreation-proof.md).

Type: task. Status: resolved on merge of the PR below (Claude, branch `claude/t151-review-counts`). Blocked by: none.

## Question

The recreation proof's stores held 3,963 reviews, and the review counts in its report summed to 3,926. The 37 others
are `unresolved_endpoint` reviews: relationship records waiting for a missing end. Should `inspection.counts` show
that reason? A steward reading the report cannot see those 37 today.

## Parts

- [x] A test states the expected counts with an `unresolved_endpoint` review present: the waiting-link scenario in `worker_publication_scenarios.py` asserts `waiting_links == {"unresolved_endpoint": 1}` and `open_reviews == {}`, then `{}` once the other end resolves; the installed `review_recovery` case passes on MySQL (2 tests, 7 min; 2026-11-01 17:47 ET)
- [x] The report counts that reason: `inspection.counts` gains `waiting_links`, by reason. Cause: a link waiting for its other end is stored `open: False, waiting_for_end: True` by design (`merge.py`, "Wait quietly", 2026-10-02), so `open_reviews` never held it, and `waiting` means set-aside records. The link is no steward's review, so it has its own key (2026-11-01 17:50 ET)
- [x] PR, CI green, merged: #1271 (the PR is the record; ticked 2026-11-04 04:42 ET)
- [x] `Learning → skill`: none; the reason is in the code comment beside the new count (2026-11-01 17:50 ET)
