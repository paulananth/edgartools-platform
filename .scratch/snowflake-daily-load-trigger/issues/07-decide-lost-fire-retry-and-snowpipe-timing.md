# Decide Lost-Fire Retry and Snowpipe-Timing Handling

Type: grilling
Status: resolved

## Question

Surfaced by the Opus design-review pass (see
[DESIGN-SUMMARY.md](../DESIGN-SUMMARY.md), findings G1 and G2). Both are
bounded by the manifest stream's durability to *delayed* sync rather than
lost data (the stream is `append_only`, and rows simply sit pending until
the next successful fire drains them) — but neither was analyzed by any
existing ticket, and "bounded but delayed" is still a real design choice
about how delayed is acceptable before ticket 04's alarm should fire.

**G1 — a lost fire has no recovery path.** [Ticket 02](02-design-idle-detection-recheck-and-race-safety.md)
analyzed the false-*idle* race (a new execution not yet visible as
RUNNING → premature fire — self-corrects, harmless) but never the
false-*busy* direction, and no ticket specifies a retry:
- If the re-check's `list-executions` still shows the just-terminated
  execution (API eventual consistency), the fire is skipped.
- If the ECS task fails to start, or the connector call errors, the fire
  is simply gone.
- [Ticket 01](01-decide-once-per-day-debounce-cap-semantics.md) keeps no
  "already fired" state and [ticket 03](03-decide-invocation-plumbing-and-task-object-fate.md)
  removes the timer that used to structurally retry every 6 hours — so
  nothing currently re-attempts a skipped transition until the *next*
  watched pipeline happens to finish (steady state: ~24h, ~48h across the
  Sunday gap in the `daily_incremental` cron).

Cheap mitigation worth deciding on: the EventBridge event payload carries
`detail.executionArn` — the re-check could explicitly exclude the
triggering execution from the RUNNING set rather than trusting API
consistency, and whatever invokes the new ECS command
([ticket 06](06-resolve-invocation-path-and-secret-plumbing.md)'s
decision) could carry an explicit retry policy.

**G2 — Snowpipe ingestion latency vs. an immediate fire.** The manifest
inbox is populated *asynchronously*: the gold ECS task writes a manifest
to S3 → SNS → `snowflake_pipe.manifest` (`auto_ingest = true`,
`main.tf:660-675`) → `SNOWFLAKE_RUN_MANIFEST_INBOX` → the stream. The
Step Functions execution reaches `SUCCEEDED` as soon as the ECS task
exits — which can be *before* Snowpipe has ingested. A fire that lands in
that gap sees an empty stream (`processed_count: 0`) and, combined with
G1's absent retry, produces nothing for that transition. This is the exact
failure mode the old 6-hour poll structurally masked (it always retried on
its next wake) — no ticket mentions Snowpipe or the inbox→stream lag at
all.

Cheap mitigation worth deciding on: have the new command poll
`SYSTEM$STREAM_HAS_DATA` for a bounded window before calling (it already
needs a warehouse session, so the marginal cost is small) vs. accept the
delay explicitly and let ticket 04's alarm be the sole backstop for the
pathological case.

Decide, for both G1 and G2: build an explicit mitigation now, or
deliberately accept "bounded by the next watched completion, backstopped
by ticket 04's alarm" as the design — and if the latter, what
"pathological" threshold ticket 04 should actually alarm on (this feeds
directly into ticket 04's own open sub-question 2).

## Answer

Build both cheap mitigations now rather than deferring everything to
delayed-sync-plus-alarm — [ticket 06](06-resolve-invocation-path-and-secret-plumbing.md)'s
resolution already changed what "cheap" means here, so re-scoped G1 into
two distinct sub-cases with different fates before deciding:

**G1a — ECS task fails to start, or the connector call genuinely errors:
already covered, no new mechanism needed.** Ticket 06 resolved invocation
as a minimal single-state SFN wrapping the ECS task, which gets
`Retry: [{"ErrorEquals": ["States.TaskFailed"], "IntervalSeconds": ...,
"BackoffRate": 2.0, "MaxAttempts": 2}]` for free from the same
`ecs_state()` helper every other task in this script already relies on.
The only implementation requirement this imposes: the new command must
**exit non-zero on a genuine failure** (connector error, unexpected
exception) and **exit 0 on a legitimate no-op** (nothing pending, or
correctly determined "not idle") — that distinction is what lets the
existing Retry block do the right thing without a bespoke retry policy.

**G1b — stale RUNNING view of the just-terminated triggering execution:
fixed by excluding the known ARN, not by trusting API consistency.**
Ticket 06's `InputPath: "$.detail"` wiring means the command already
receives `detail.executionArn` as part of its SFN input. **The command
excludes that specific ARN from its own `list-executions
--status-filter RUNNING` result before deciding idle/not-idle** — since
that ARN is known-terminated by construction (it's the event that just
triggered this very invocation), there's no reason to depend on whether
the API's list has caught up yet for that one entry. This removes the
false-busy case outright rather than leaving it to the delayed-sync
fallback.

**G2 — bounded poll on `SYSTEM$STREAM_HAS_DATA` before giving up.** The
command already opens a Snowflake session to make the eventual `CALL`
regardless, so checking `SYSTEM$STREAM_HAS_DATA('...SNOWFLAKE_RUN_MANIFEST_STREAM')`
a few times (~15-20s interval, ~2 minute bound) before proceeding is a
marginal cost, not a new dependency. If the bound is exceeded, proceed
anyway — `PROCESS_RUN_MANIFEST_STREAM()` is a safe no-op on an empty
stream (per ticket 01's finding), so there's no failure case to handle,
just an accepted possibility that this particular fire drains nothing and
the next watched completion picks up the backlog. This is a genuine
freshness improvement over "always accept the delay" for the common case
(Snowpipe auto-ingest latency is typically seconds, occasionally longer
under load) without the operational cost of an unbounded wait or a new
polling infrastructure.

**Consequence for [ticket 04](04-design-dead-mans-switch-alarm.md):**
with both mitigations in place, the alarm's threshold no longer has to
compensate for routine G1/G2 cases — those are now handled within the
same fire, in the common case. The alarm's job narrows to genuinely
pathological situations: a Snowpipe delay exceeding the ~2 minute bound
*and* no other watched pipeline completing for an extended period, a
persistent connector/credential failure surviving the SFN's 2 retry
attempts, or an EventBridge rule misconfiguration. This should make
ticket 04's threshold question easier — it's answering "how long is too
long once the cheap mitigations have already had their shot," not
"how long is too long given zero mitigation."
