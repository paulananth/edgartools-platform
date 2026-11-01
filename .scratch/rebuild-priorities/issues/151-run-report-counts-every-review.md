# 151: The run report counts every open review

Priority: 151. Map: [Rebuild priorities](../map.md). Opened 2026-11-01 11:03 ET, from [ticket 32](32-profiling-08-recreation-proof.md).

Type: task. Status: open. Blocked by: none.

## Question

The recreation proof's stores held 3,963 reviews, and the review counts in its report summed to 3,926. The 37 others
are `unresolved_endpoint` reviews: relationship records waiting for a missing end. Should `inspection.counts` show
that reason? A steward reading the report cannot see those 37 today.

## Parts

- [ ] A test states the expected counts with an `unresolved_endpoint` review present
- [ ] The report counts that reason, or the ticket records why it does not
- [ ] PR, CI green, merged
- [ ] `Learning → skill`
