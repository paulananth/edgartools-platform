# Is the 7-day Canonical Silver noncurrent rule enough after the one-shot?

Type: grilling
Status: resolved
Blocked by: none

## Question

After SHARD-01 deleted already-superseded noncurrent `shard-*.duckdb`
versions, should standing lifecycle on `warehouse/silver/` keep
noncurrent versions for **7 days**, or should the window shorten so
overwrite storms drain faster?

Decide:

1. Keep 7-day Canonical Silver *noncurrent* expiration. No current-object
   expiration. One-shot reclaim does not change the standing window.
2. Shorten the standing noncurrent window (name the day count) now that
   the backlog is gone.
3. Something else (separate rule, Glacier, keep-N versions).

Current Canonical Silver keys must not be deleted. Do not apply Terraform
while resolving this ticket.

## Answer

**Option 1.** The standing 7-day Canonical Silver noncurrent rule is
enough after the one-shot. Do not shorten it. Current Canonical Silver
still has no expiration. Prefix stays `warehouse/silver/` with a trailing
slash.

Why not 2 or 3: Leak-seal already locked 7-day noncurrent as the drain for
future shard overwrite storms. SHARD-01 was a one-shot of the backlog, not
a standing-policy change. A shorter window is a new cost/forensics trade
and is out of this map.

Covered by
`test_canonical_silver_rule_expires_only_noncurrent_after_seven_days`.
