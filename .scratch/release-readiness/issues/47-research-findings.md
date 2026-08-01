# Ticket 47 research findings — silent-overwrite window after the prodb→prod cutover

## Scope and outcome

This read-only investigation covers canonical bronze writes between **2026-07-19
00:00 UTC** and **2026-07-29 00:00 UTC**. It asks whether an already-migrated
filing artifact was re-fetched through the post-ticket-06 `attachment.content`
path before PR #298 made writes immutable, thereby silently replacing the
byte-exact migrated bytes.

**Outcome: no confirmed silent overwrite was found.** The complete relevant
Step Functions execution history identifies no `bootstrap*`, `load_history`,
`targeted_resync`, daily-index, or repair execution in the window. The only
relevant workflow executions were the Ticket 20 relationship-release runs.
Their inputs are frozen candidate-manifest/batch keys; their recorded end-state
evidence has zero remaining batch items and zero SEC network fetches. The
earliest Ticket 20 Map run after cutover failed before a successful item and
did not establish an artifact-write candidate.

This is a strong negative result for **recorded state-machine work**, but not a
mathematical proof over every S3 key: the source bucket's 1,181,412 versions
were intentionally purged during the same cutover session, and a full
canonical-prefix noncurrent-version scan did not return a usable aggregate in
this pass. A future repair decision should perform that paginated inventory if
it needs a universal proof rather than the present execution-bound conclusion.

## Primary evidence

1. The cutover record [`02-perform-stage2-s3-data-copy.md`](../../prodb-prod-cutover/issues/02-perform-stage2-s3-data-copy.md)
   records a one-time, server-side `aws s3 sync` after Ticket 20 was quiescent,
   preserving keys and matching **433,681 current bronze objects** and
   **39,362,929,987 bytes** source-to-target. It also says only current
   versions were copied.
2. The cutover decommission record
   [`06-decommission-old-prodb-bucket-and-objects.md`](../../prodb-prod-cutover/issues/06-decommission-old-prodb-bucket-and-objects.md)
   records 1,181,412 prodb-bronze versions purged only after the same 433,681
   current-object parity check. Therefore source-side version history cannot
   now identify a hypothetical pre-copy transition.
3. Live, read-only AWS inspection on 2026-07-31 using `sec_platform_deployer`
   confirmed `edgartools-prod-bronze-690839588395` versioning is `Enabled`.
   The Apple control key
   `warehouse/bronze/filings/sec/cik=320193/accession=0000320193-26-000011/primary/aapl-20260430.htm`
   retains the migration version at `2026-07-19T20:13:22Z`, 37,639 bytes,
   plus only later versions from 2026-07-31. It has **no** version dated in the
   investigated 2026-07-19–2026-07-28 interval after the copy. This directly
   confirms that the known collision did not silently overwrite during the
   vulnerable interval.
4. Live `list-executions` over the relevant prod state machines found no
   `bootstrap`, `bootstrap-batched`, `bootstrap-full`, `load_history`,
   `targeted_resync`, `daily_incremental`, `catch-up-daily-form-index`, or
   `load-daily-form-index-for-date` execution in the window. The only result
   was `edgartools-prod-bronze-seed-silver-gold` Ticket 20 executions.
5. The earliest post-cutover Ticket 20 execution,
   `ticket20-strict-gatev2-20260719T135202Z`, had a Distributed Map run from
   `2026-07-19T09:52:12-04:00` to `11:17:08-04:00`. Live
   `describe-map-run` shows 125 items: zero succeeded, one failed, four
   aborted, and 120 pending. Its `States.ExceedToleratedFailureThreshold`
   failure occurred before the later successful workflow path.
6. The succeeding endpoint-seal execution's live history begins with
   `reconcile-relationship-release` and then MDM/gold commands; it does not
   schedule a filing-artifact capture command. Its committed completion
   evidence, [`ticket20-completion-evidence-2026-07-25.json`](../../../docs/release-readiness/ticket20-completion-evidence-2026-07-25.json),
   records `StrictBatchSilver_map_items: 0` and `sec_network_fetches: 0`.
7. Repository history explains why the risk was real but bounded: before PR
   #298, `_write_raw_artifact` called `write_bytes`, an ordinary S3 write;
   PR #298 (`e0fa0ea`, 2026-07-28) switched it to conditional
   `write_immutable_bytes`. Ticket 06 (`f6c40f1`, 2026-07-17) had already
   moved artifact content to edgartools' normalizing path. Thus a re-fetch
   would have been capable of overwriting, but the execution evidence does
   not show a production workflow that did so in this interval.

## Limitations

- Step Functions history proves the relevant managed workflows, not an
  out-of-band ECS `run-task`, direct S3 `PutObject`, or a log-retention-expired
  action. No such action was identified from the repository evidence.
- The Apple key is a direct retained-version control, not a whole-bucket
  proof. A complete canonical `list-object-versions` aggregation over all
  filing prefixes was attempted read-only but did not yield a usable aggregate
  within this pass; no claim is made that it found zero noncurrent versions
  across every key.
- The purged prodb versions mean no after-the-fact comparison can recover a
  source-side predecessor for an unlisted candidate.

## Recommendation

Treat this ticket's question as **not confirmed, with no evidence of an
in-window managed-workflow overwrite**. Do not start a repair merely from the
theoretical pre-guard risk. If operator GO requires universal assurance,
graduate a narrowly scoped follow-up: paginate canonical `list-object-versions`
for `warehouse/bronze/filings/sec/`, select noncurrent versions whose
`LastModified` is inside the window, then byte-compare each version pair and
cross-reference its accession against ECS/CloudWatch provenance. That work
should remain read-only until an actual differing pair is demonstrated.
