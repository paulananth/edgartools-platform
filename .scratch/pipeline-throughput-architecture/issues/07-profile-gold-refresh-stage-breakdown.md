Type: task
Status: open

## Question

Get a real, measured per-table timing breakdown for one full `gold-refresh`
run: how long each of the ~24 `iter_gold_tables` builders takes, plus the
fixed cost of copying/reading the canonical silver file (currently 1GB+,
same local-copy pattern `silver_protection.py` uses) before any table build
starts.

Split off from [ticket 04](04-decide-cross-task-fanout-model.md): that
ticket's `gold-refresh` fan-out question can't be answered responsibly
without this data. Ticket 01 profiled `daily-incremental` only (the
pipeline that happened to be running live during that investigation) --
`gold-refresh` has never been profiled this way.

The real tradeoff [ticket 08](08-decide-gold-refresh-fanout.md) needs
numbers for: fanning out table builds across N ECS tasks means N separate
copies of the canonical silver file, not one. Whether that's worth it
depends entirely on how expensive the table builds themselves are relative
to that fixed copy cost -- guessing either way would break this map's own
standing rule (every decision backed by real measured data, not structural
reasoning alone).

## Done when

A written per-table (or reasonably grouped) timing breakdown from a real
`gold-refresh` run, plus the measured file-copy/read cost, that
[ticket 08](08-decide-gold-refresh-fanout.md) can cite as evidence.
