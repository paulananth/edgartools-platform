# Decide Migration/Cutover Strategy From Monolith to Sharded Primary Writes

Type: grilling
Status: open
Blocked by: 01

## Question

**Scope note (post ticket 05):** the map's destination narrowed to just
`load_history`'s `WindowedBootstrap` and `bootstrap_fundamentals.py`'s three
Stage 1B modes — `daily_incremental`/`bootstrap` are out of scope. Read this
question with that narrower scope; ticket 05 also decided monolith retention
during the transition (migrate every consumer first, then cut over cleanly
— not dual-write) and the safety gate (shadow/dry-run with N consecutive
clean diffs against `migrate_silver_shards.py`'s existing 3-layer
verification) — don't re-decide those here, this ticket is about the
mechanics of the transition itself, not whether/how to gate it.

`migrate_silver_shards.py` already exists and was used as a one-time
operational command to produce the 4 shard files currently in S3. Once
`WindowedBootstrap`/`bootstrap_fundamentals.py` start writing via the shard
path instead of the monolith, how does the *transition* happen safely:

- Is `migrate_silver_shards.py` re-runnable against a live, growing dataset
  (not just a clean initial split), or does flipping a primary command onto
  the shard path require a coordinated one-time re-split first?
- What's the safety net if a command's first sharded-write attempt fails
  partway (e.g. shard 2 of 4 published successfully, shard 3 failed) — does
  the existing ETag-guarded per-shard publish (`_publish_shard_if_remote`)
  already handle this, or does a new coordination mechanism need to exist
  across shards for one logical publish?
- Does the monolith file need to stay in sync during a transition period
  (e.g. dual-write), or can it be cut over cleanly once ticket 02's consumer
  compatibility is confirmed?

## Deliverable

A decision, recorded on resolution: the transition mechanism, and what (if
anything) needs building beyond what `migrate_silver_shards.py` /
`_publish_shard_if_remote` already provide.
