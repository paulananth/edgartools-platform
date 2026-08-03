Type: grilling
Status: open

Blocked by: 01, 02

## Question

Should per-CIK network+DB operations inside a single ECS task move from
today's sequential Python loop (one CIK/accession at a time, e.g.
`_capture_submission_bronze_snapshot`, the artifact-fetch loop in
`bronze_filing_artifacts.py`) to intra-task concurrency (asyncio or a
bounded thread pool), given the SEC rate-limit ceiling ticket 02
establishes?

If [Profile the real bottleneck breakdown across pipeline
stages](01-profile-pipeline-stage-bottleneck-breakdown.md) shows the
per-CIK loops are already running at the rate-limit ceiling (throughput
bound by SEC, not by Python), added concurrency inside one task buys
nothing and this ticket should resolve "no" with that evidence. If it
shows meaningful idle time between requests (DB writes, JSON parsing,
orchestration overhead not overlapped with the next fetch), concurrency
is the lever and this ticket should specify the shape (asyncio vs
threadpool, what bound, which loops).

## Done when

A decision -- yes/no, and if yes, which loops and what concurrency
primitive/bound -- backed by ticket 01's measured breakdown, not
estimation.
