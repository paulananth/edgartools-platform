# Spec: Record unclosed reclaim-map decisions

**Status:** ready-for-agent
**Type:** spec
**Label:** ready-for-agent
**Date:** 2026-08-21
**Repo:** edgartools-platform
**Map:** [Warehouse S3 Duplicate-Storage Reclaim](map.md)
**Parent spec:** [Warehouse S3 Duplicate-Storage Reclaim](spec.md)

## Problem Statement

From the operator's perspective: leak-seal and VersionId Reclaim already
shipped, but the wayfinder map still looks unfinished. Three decisions were
used as defaults in the parent spec and in the live tool, then never written
onto their tickets or into Decisions so far. Anyone reading the map cannot
tell whether Identity Refresh Run skip, the ADR 0004 contract, or the
seven-day Canonical Silver noncurrent window are still open. The map is the
index; unanswered tickets look like live risk.

## Solution

Close the map on paper to match what already shipped. Record three answers
on child tickets, gist them on the map, and clear the matching fog. Do not
change Terraform, do not delete objects, do not change reclaim selectors.

1. One-shot Identity Refresh Run skip is newest-object age of 24 hours on
   the run directory under the identity-refresh prefix. Standing 7-day
   lifecycle still does not skip RUNNING maps.
2. ADR 0004 stays staging-only (`IsLatest=true` under the ephemeral prefix,
   confirm flag for staging). Warehouse duplicates use the sibling VersionId
   Reclaim contract (Canonical Silver deny-list, identity age skip, gold
   keep-set).
3. After the one-shot shard reclaim, the standing 7-day Canonical Silver
   *noncurrent* rule is enough. Do not shorten it.

## User Stories

1. As a platform operator, I want the identity-skip decision on its own
   ticket, so that I do not re-grill whether to poll Step Functions.
2. As a platform operator, I want one-shot reclaim to skip an Identity
   Refresh Run whose newest object is younger than 24 hours, so that an
   in-flight reducer is not deleted mid-run.
3. As a platform operator, I want that skip keyed on the run directory's
   newest LastModified, so that I do not need a live execution API during
   dry-run.
4. As a platform operator, I want Identity Refresh leases outside the
   identity-refresh prefix left alone, so that slot bookkeeping is not
   treated as a run snapshot.
5. As a platform operator, I want standing 7-day identity expiry to stay
   a hard clock, so that lifecycle does not try to detect RUNNING maps.
6. As a reviewer, I want the map to say the 24-hour skip is the answer, so
   that a later agent does not "fix" it to a lease-file check.
7. As a platform operator, I want ADR 0004 to remain staging-only, so that
   `IsLatest=true` cannot be pointed at Canonical Silver shards.
8. As a platform operator, I want the staging cleanup confirm flag to stay
   distinct from the duplicate-reclaim confirm flag, so that a typo cannot
   run the wrong selector.
9. As a platform operator, I want warehouse-duplicate reclaim to stay a
   sibling contract, so that deny-list and keep-set stay explicit.
10. As a reviewer, I want a test that the staging script still contains
    `IsLatest=true` and the staging confirm flag, so that a copy-paste
    merge cannot silently share selectors.
11. As a platform operator, I want Canonical Silver current objects never
    expired by lifecycle, so that the live typed store cannot vanish.
12. As a platform operator, I want Canonical Silver noncurrent versions to
    keep expiring after 7 days, so that shard overwrite storms drain without
    another one-shot.
13. As a platform operator, I want that 7-day window unchanged after the
    one-shot shard reclaim, so that Terraform does not grow a second,
    shorter noncurrent rule.
14. As a reviewer, I want the architecture test to keep asserting
    noncurrent-only 7 days and no current expire on the silver prefix, so
    that a "cost" follow-up cannot shorten the window in HCL unnoticed.
15. As a map reader, I want fog about "is 7 days enough" removed, so that
    I do not treat it as an open decision.
16. As a map reader, I want fog about `/to-spec` slicing and evidence
    location left only if still unknown; evidence already lives under the
    warehouse release-evidence prefix, so that stale fog does not look like
    unfinished reclaim.
17. As an agent, I want tickets 03 and 06 created on this branch if they
    are missing, so that Decisions so far can link to a real issue file.
18. As an agent, I want a new child ticket for the 7-day noncurrent
    question, so that a fog patch does not get answered only in the spec.
19. As a map reader, I want each closed ticket titled as a question, so
    that the index stays readable without ids.
20. As a map reader, I want one-line gists on Decisions so far, so that I
    can judge relevance without opening every body.
21. As a future operator, I want gold dual-write stop and reclaim-all of
    warehouse gold out of this spec, so that this closeout cannot reopen
    GOLD-01 keep-latest.
22. As a future operator, I want empty silverstage multipart-upload abort
    out of this spec, so that 0-byte hygiene is not mixed with decision
    recording.
23. As a CI system, I want existing unit and architecture tests to stay
    green with no new AWS credentials, so that closeout cannot require a
    prod apply.
24. As a reviewer, I want no MDM working-tree files in this change, so
    that credential or resolver WIP does not land in a planning commit.

## Implementation Decisions

- This spec records decisions; it does not add a fourth reclaim selector or
  a new lifecycle day count.
- Seam: the wayfinder map and its child tickets. Runtime behavior already
  matches the three answers. Do not introduce a second skip mechanism
  (Step Functions, ECS task command, or lease JSON) for the one-shot.
- Identity skip signal: among objects whose key is under the identity-refresh
  run prefix, group by run directory; if that group's newest LastModified
  is younger than 24 hours relative to reclaim `now`, skip every object in
  that run. Unique current keys (they never become noncurrent by overwrite)
  are still eligible when older than 24 hours.
- Do not read Identity Refresh lease objects for the skip. Those keys live
  under the reference lease prefix, not the identity-refresh snapshot prefix.
- Standing identity lifecycle remains 7 days current and noncurrent on the
  snapshot prefix only. Leak-seal D-07 (hard expire, no RUNNING skip) is
  unchanged.
- ADR 0004 remains the one-time staging cleanup: ephemeral prefix,
  `IsLatest=true`, staging-specific confirm flag. Do not add Canonical
  Silver deny-list or gold keep-set to that script.
- Sibling VersionId Reclaim remains the warehouse-duplicate contract:
  current Canonical Silver keys denied; noncurrent Canonical Silver
  versions eligible; identity age skip; gold keep-set as already shipped.
  Distinct confirm flag from staging.
- Canonical Silver standing rule stays noncurrent-only, 7 days, trailing-slash
  silver prefix. One-shot SHARD-01 does not justify a shorter standing window.
  Current Canonical Silver still has no expiration.
- Map updates: append gists for the three tickets under Decisions so far;
  remove fog lines about `/to-spec` slicing (already sliced), evidence
  location (release-evidence prefix), and "is 7 days enough" (answered: yes).
- If child files for identity skip and sibling contract are missing on the
  branch, create them with Type grilling, Status resolved, and an Answer
  that matches this spec. Number them as originally charted (03, 06). Add
  one new grilling ticket for the 7-day noncurrent question (next free
  number at or after 11).
- Parent spec Further Notes still say "remaining open grilling" for these
  items; that sentence must be updated so the parent spec and the map
  agree.
- No Terraform apply, no VersionId delete, no CloudWatch change, no gold
  dual-write removal in this spec.

## Testing Decisions

- Good tests already assert observable contracts, not helper names: identity
  run dirs newer than 24 hours are absent from `select_candidates`; staging
  cleanup script still has the staging confirm flag and `IsLatest=true`;
  warehouse lifecycle HCL has silver noncurrent 7 days and no current-object
  expiration. Closeout must not weaken those tests.
- Seam under test is `select_candidates` (fixture listings) and the
  architecture test that parses warehouse lifecycle HCL. Prior art: existing
  reclaim unit tests and warehouse lifecycle prefix architecture tests.
  Do not add a live AWS test.
- A map/ticket closeout is done when: the three tickets are Status
  resolved with Answer sections; Decisions so far has three gists; fog no
  longer lists the three items; parent spec Further Notes no longer call
  them open; `uv run pytest` on the reclaim unit file and the lifecycle
  architecture file still passes.
- Do not add a tautological test that re-reads the markdown Answer.

## Out of Scope

- Stopping the warehouse-bucket gold dual-write.
- Reclaiming remaining `warehouse/gold/` with no keep-latest.
- Aborting empty silverstage multipart uploads.
- Shortening or lengthening any standing lifecycle day count.
- Changing Identity Refresh Run skip from 24-hour age to lease or
  Step Functions detection.
- Extending ADR 0004 to Canonical Silver or gold.
- Deleting current Canonical Silver or current bronze SEC objects.
- CloudWatch retention.
- Re-opening GSD Leak-seal D-01–D-17.
- Mixing MDM working-tree files into the closeout commit.

## Further Notes

- Vocabulary: Canonical Silver, Joined Live Key, VersionId Reclaim, Staged
  Warehouse Object, Identity Refresh Run — root CONTEXT.md.
- Parent spec already encoded these three as implementation defaults
  (24-hour skip; sibling not ADR 0004; 7-day silver noncurrent out of
  scope to shorten). This spec only makes the map tell the same story.
- GSD workstream `s3-silverstage-lifecycle` is archived under
  `.planning/milestones/ws-s3-silverstage-lifecycle-2026-08-21/`. Do not
  resurrect it to record these answers; the wayfinder map is the index.
