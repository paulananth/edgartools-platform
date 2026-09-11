Type: research
Status: resolved

Blocked by: 07, 09, 10

## Question

Graduated from the map's own "Not yet specified" fog: Ticket 04 found that
`snowflake_graph.py`'s parity checks have the identical quarantine-blindness
omission on their "expected" side as the graph-build query itself — so
`MDM_MINUS_GRAPH = 0` can read as clean even when it isn't. Ticket 07 fixed
the code. Tickets 09 and 10 then each ran a real prod backfill followed by
a manual graph rebuild, both reporting "exact parity confirmed."

Was Ticket 07's fix actually **live** in the deployed MDM image for those
two rebuilds, or did they run against the still-buggy code — meaning
their "exact parity confirmed" claims are the exact false-clean signal
Ticket 04 warned about, not real confirmation? Ticket 09's own file never
records a deploy step, so this wasn't verified at the time, only assumed.

## Answer

**Verified via ECR/ECS live records (not inferred from git alone): yes,
the fix was live before both rebuilds ran — the parity confirmations are
real, not false-clean.**

- Ticket 07's fix is commit `9984cc5a` (2026-09-08T18:06 ET). It was built
  and pushed as `mdm-sha-9984cc5a8d9e` at 18:36 ET the same day (confirmed
  via `aws ecr describe-images`).
- The real INSTITUTIONAL_HOLDS backfill (Ticket 09) needed a *later* fix
  too — the `resolve_source_priority` caching fix, commit `d1ae9a01`
  (2026-09-10T06:14 ET) — for its real run to complete in reasonable time.
  `git merge-base --is-ancestor 9984cc5a d1ae9a01` confirms `9984cc5a` is
  an ancestor, so any image containing the cache fix necessarily contains
  Ticket 07's fix too.
- `edgartools-prod-mdm-large:194` was registered at **2026-09-10T06:17:07
  ET**, pointing at image digest `sha256:a5cfce6aca4b8...` — which matches
  `mdm-sha-448e7c95b9e5` (PR #579's merge commit, which includes both
  `d1ae9a01` and `9984cc5a`). This was live **before** the real backfill
  task started (06:32 ET) and well before either rebuild ran (Ticket 09's
  same-day rebuild after the ~1h46m backfill finished ~08:18 ET; Ticket
  10's rebuild later the same day).
- No task definition revision between `9984cc5a`'s push (2026-09-08
  18:36 ET) and both rebuilds ever reverted to an older image — the
  revision history is monotonically forward (`189` → `194`, each pointing
  at a newer digest, never backward).

**Conclusion:** both "exact parity confirmed" claims in Tickets 09 and 10
are trustworthy. No targeted correction pass is needed for the duplicate
graph edges Ticket 04 found — the explicit manual rebuild each ticket
already performed, using already-fixed code, was sufficient and is
confirmed to have worked, not just assumed to have worked.

**Second half of the original fog question — is a post-backfill graph
rebuild automatic or must it be manually triggered?** Confirmed manual,
not automatic: both Ticket 09 and Ticket 10 each ran `mdm
publish-relationships` → `mdm reconcile --generation-id` → `mdm
graph-activate` as an explicit follow-up step after their Postgres-side
backfill, via nothing that the backfill CLI itself triggers. Nothing in
`relationship_quarantine_backfill.py`'s CLI wires this — an operator who
runs the backfill and forgets the rebuild step leaves stale duplicate
edges live indefinitely with no automated correction and no alert. Not
fixed here (no evidence yet that anyone actually forgot it in practice) —
noted as new fog, not a ticket, below.

**Adjacent, deliberately not addressed here:** CLAUDE.md's own "Two
graph-generation activation paths, now out of sync" entry documents that
Postgres's `mdm_graph_generation` table still shows a stale generation
(`9bc1d71d-...`) as `activated` even though Snowflake's actual active
pointer is correct — a different, already-tracked gap (which generation
tracking *table* is authoritative), not a graph-content-correctness
question like this ticket. Left as-is per that entry's own note.
