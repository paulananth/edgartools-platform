# Proposed Rollback Cohort Validation — 2026-08-09

## Question and scope

Can this exact six-task-definition cohort be treated as a known-good rollback
release based on repository-owned evidence?

| Runtime/profile | Task definition | Immutable image identity |
| --- | --- | --- |
| warehouse small | `edgartools-prod-small:159` | `sha256:a493e0d183f4bd1d5a01f46034b2250d76830206b49672b5f14d9a35080e504e` / `warehouse-sha-b64f1de5a660` |
| warehouse medium | `edgartools-prod-medium:164` | same warehouse image |
| warehouse large | `edgartools-prod-large:157` | same warehouse image |
| MDM small | `edgartools-prod-mdm-small:137` | `sha256:cc64ba854ee382256fe7f58381f57feadd923645507bac53cf7e0c57a4e4640a` / `mdm-sha-3f009d0af82a` |
| MDM medium | `edgartools-prod-mdm-medium:138` | same MDM image |
| MDM large | `edgartools-prod-mdm-large:72` | same MDM image |

The repository review used checked-in files and local Git history. A follow-up
read-only AWS audit on 2026-08-09 queried ECR, ECS, Step Functions, and
CloudWatch Logs in account `690839588395`, region `us-east-1`. It did not start
an execution, change a definition, deregister a revision, or designate the
cohort.

## Conclusion

**No. The repository does not prove that this exact cohort was a known-good,
end-to-end rollback release.** It proves that the six revisions and immutable
ECR tags existed as one captured pre-handoff live cohort, and it contains useful
stage-level evidence from the same period. It does not bind that evidence to
these six revisions, one frozen Step Functions definition set, and one complete
successful execution.

The gap is stronger than missing paperwork: the only live execution in the
cohort's deployment window used its exact revisions and **failed** before graph
and gold completion. Both immutable images also predate subsequent fixes for
production-observed behavior. The MDM image predates a reproduced `mdm run`
rerun crash fix, and the warehouse image predates the fix that stopped
`gold-verify-live` from rejecting intentionally empty pilot-only tables.
Consequently, this cohort should remain provisionally protected from cleanup
as recovery evidence until the replacement decision is persisted, but it must
not be finalized as the known-good rollback release.

## Live identity and execution findings

### The binaries and all six revisions remain recoverable

Read-only ECR queries confirmed both immutable digests and source tags still
exist:

- warehouse digest `sha256:a493e0d...e504e`, tag
  `warehouse-sha-b64f1de5a660`, pushed 2026-08-08 12:13:58 EDT;
- MDM digest `sha256:cc64ba85...4640a`, tag
  `mdm-sha-3f009d0af82a`, pushed 2026-08-08 17:41:00 EDT.

Read-only ECS queries confirmed all six proposed revisions are still `ACTIVE`,
have the expected digest, and were registered together from 17:54:53 through
17:55:01 EDT. Their resource profiles remain `512/1024`, `1024/4096`, and
`2048/8192` for small, medium, and large respectively.

### The sole execution in the exact deployment window failed

Across all 26 production state machines, only one execution started after the
six revisions were registered and before the next image rollout began:

`arn:aws:states:us-east-1:690839588395:execution:edgartools-prod-bronze-seed-silver-gold:bronze-seed-silver-gold-1786226258`

It started at 2026-08-08 17:57:39 EDT and ended `FAILED` at 2026-08-09
07:36:22 EDT. Preserved Step Functions task-scheduling parameters bind it to
`edgartools-prod-medium:164` and `edgartools-prod-mdm-medium:138`, rather than
requiring a chronology inference.

The execution provides limited positive stage evidence: `seed-bronze-batches`,
`mdm run`, and `mdm backfill-relationships` completed. The Distributed Map had
length zero, so it did not validate a BatchSilver child workload. Four
successive `mdm export` attempts on `mdm-medium:138` exited 1, and the execution
failed before graph or gold stages.

CloudWatch log streams for all four failed ECS tasks report the same terminal
Snowflake error:

`Object 'EDGARTOOLS_PROD.MDM.MDM_ENTITY' does not exist or not authorized.`

This may have been an external schema/grant readiness failure rather than an
image defect, but it still means the exact cohort was never demonstrated to
complete against the production downstream contract. A rollback release must
restore a usable full chain, not merely launch its containers.

Nearby successes do not qualify. `mdm-run-perf-measure-1786282750` used
`mdm-medium:140` on digest `sha256:6a38edf1...107b`; the Stage 15 gold refresh
used `large:160` on the newer warehouse digest `sha256:86f51103...c625`; and
the later MDM E2E run that reproduced the rerun failure also used
`mdm-medium:140`. None used the proposed MDM digest.

### Two prior cohorts are exact task-definition duplicates of current

The read-only audit also found two complete six-revision cohorts on today's
current warehouse and MDM digests:

| Cohort | Warehouse small/medium/large | MDM small/medium/large |
| --- | --- | --- |
| earlier duplicate | `164` / `168` / `161` | `141` / `141` / `75` |
| later duplicate | `165` / `169` / `162` | `142` / `142` / `76` |
| current | `166` / `170` / `163` | `143` / `143` / `77` |

After removing only AWS registration metadata (`taskDefinitionArn`, revision,
status, timestamps, registrant, compatibility annotations), each profile's
canonical JSON SHA-256 is identical across all three cohorts. They are valid
control-plane recovery candidates because they reproduce current task
configuration and immutable images. They are **not** an independent code
rollback, and adjacency alone is not their evidence; canonical byte-equivalence
is.

## Evidence that does exist

### 1. Immutable identity and availability were captured

The post-handoff reconciliation records all six exact task revisions, both
digests, and both source tags, and says the revisions remained active and the
immutable tags remained in ECR at capture time
(`.scratch/ecs-cost-sizing/research/task-definition-reference-reconciliation-2026-08-09.md:214-233`).
That is strong evidence of identity and recoverability of the binaries. It is
not execution-success evidence. The same audit explicitly calls the cohort
provisional and states that no durable release manifest or complete
end-to-end-success evidence was found (`...task-definition-reference-reconciliation-2026-08-09.md:227-233`).

A repository-wide exact-identity search found the proposed digests/source tags
in only two pre-existing files: that reconciliation and the unresolved cohort
decision ticket. There is no checked-in Candidate Evidence Set under
`docs/release-readiness/releases/` for these identities.

### 2. The warehouse source commit has tests, but its own history disclaims live proof

Warehouse source tag `warehouse-sha-b64f1de5a660` maps to commit
`b64f1de5a66078a2603e6c69305382364313cfe8`, which implemented shard-aware
batch scheduling and changed `BatchSilver` to `MaxConcurrency=4`. Its commit
message records `1109 passed, 4 skipped`, but also says the change did not
affect the currently running execution and that nothing in the commit was
deployed yet. Unit/architecture success therefore establishes source-level
confidence, not a live release pass.

Later, repository evidence records a real `BatchSilver` run at
`MaxConcurrency=20` on the medium profile with **680/680 batches successful and
zero failures**
(`.scratch/pipeline-throughput-architecture/issues/12-decide-shard-aware-batch-scheduling.md:215-236`).
The trace of one child task also records successful hydrate, bronze, silver,
publish, and teardown timings
(`.scratch/pipeline-throughput-architecture/issues/11-profile-batchsilver-per-batch-merge-overhead.md:80-105`).
This is valuable stage evidence. Neither artifact records the exact image
digest, task-definition revision, frozen state-machine definition hash, or the
outcome of the downstream `MdmRun` through `GoldRefresh` chain. It cannot bind
the 680/680 result to `medium:164`, and it cannot elevate one successful Map
state into a complete workflow pass.

### 3. The MDM source commit has tests, but its projected live result was unverified

MDM source tag `mdm-sha-3f009d0af82a` maps to commit
`3f009d0af82a9e22227769fc2a857b3585ca0376`, which parallelized company
resolution. Its commit message records `1894 passed, 4 skipped`, but labels the
projected 37-hour to 4.7-hour improvement **unverified until run live**. It also
leaves security and person resolution on the earlier single-threaded path.

The production execution preceding this fix was aborted mid-`MdmRun`; its
roughly 1,000 of 62,190 company results were lost and the workflow restarted
from Stage 0 (`.scratch/pipeline-resumability/map.md:23-34`). A later note says
the newly running production workflow started before the subsequent
security/person image was built and leaves open whether to restart it or allow
the old code to finish (`.scratch/mdm-run-throughput/map.md:34-46`). This is
evidence of partial execution and active observation, not a recorded final
`SUCCEEDED` result. Inferring that this running execution used the proposed MDM
digest is plausible from chronology, but no checked-in execution manifest binds
it, so the inference cannot qualify the cohort.

### 4. The standing rollback rehearsal proves the mechanism, not this cohort

The checked-in rollback rehearsal passed the ordinary digest-restore mechanism
in 5m37s and records six task definitions plus 26 state-machine updates
(`docs/release-readiness/rollback-rehearsal.json:3-20`). Its concurrency proof
used warehouse tags `sha-19e7ad9f6e50` and `sha-48d761abe60d` with
`medium:89` and `medium:86`, not the proposed August revisions
(`docs/release-readiness/rollback-rehearsal-batchsilver-overlap-evidence.json:3-16`).
It proves that the deploy path and transition-safe silver publication worked for
that older pair. It does not prove the proposed warehouse/MDM binaries or their
end-to-end compatibility.

## Evidence that prevents designation

### Known MDM correctness defect after `3f009d0a`

Commit `ee62a968c7addb279aa4f8b2b513d126f3de0525` fixes an immutable-image
relevant defect absent from `3f009d0a`: after an adviser resolves, a fund's
nullable dedup key can change, causing a rerun to miss the existing fund and
attempt the same primary-key insert. The commit states that the resulting
`sqlalchemy.exc.IntegrityError` was reproduced in production on 2026-08-09 by
`mdm run --entity-type all --limit 5`, and adds a regression test that fails on
the pre-fix code. The proposed MDM digest is immutable and cannot contain this
later fix. A successful earlier stage or first pass cannot prove rerun safety
against this known failure.

The proposed MDM image also predates commit
`e244a5712f65058f280df6e8b37f3c1639b5723e`, which safely parallelizes
security/person resolution and raises the resolver/pool budget. That omission is
primarily a completion-speed and operability regression, but speed to complete
is a co-equal optimization priority and the old path lacks a recorded full-run
duration (`.scratch/mdm-run-throughput/map.md:20-46`).

### Known warehouse end-to-end gate correction after `b64f1de5`

Commit `98adb78127e19a0442f2b1c818cf183194913d15` removes
`CONSENSUS_ESTIMATES` and `TRANSCRIPT_EVENTS` from `GOLD_LIVE_TABLES` because
they are pilot-only and have no standard automated producer. Its commit message
states that the pre-fix behavior blocked Stage 15 on tables correctly empty by
design. The proposed warehouse image predates this correction. The 680/680
`BatchSilver` result does not exercise or clear this downstream gold gate.

## Missing evidence

The exact cohort lacks all of the following:

1. An append-only release manifest binding one integration commit, both image
   digests, all six task-definition ARNs, the 26 frozen state-machine
   definitions/revision IDs, and one release data watermark. The repository's
   contract requires exact commit/image identity and treats any commit or image
   change as a new candidate
   (`.scratch/release-readiness/issues/01-define-release-evidence-manifest.md:13-28`).
2. A fresh execution ARN whose frozen ASL demonstrably references these six
   revisions.
3. One terminal `SUCCEEDED` workflow covering warehouse, MDM, export, graph
   sync/verification, gold refresh, and downstream acceptance, with every
   caught state inspected so a top-level success cannot mask a failed stage.
   The release contract explicitly says one stage cannot substitute for another
   and requires a new execution name after failure
   (`.scratch/release-readiness/issues/06-define-full-chain-launch-gate.md:27-88`).
4. Output evidence: source/bronze/silver counts, export manifest, MDM publication
   watermark, graph generation/parity, gold verification, semantic digests, and
   an idempotent rerun.
5. Exact-profile evidence for warehouse small/large and MDM small/large. The
   available August live evidence principally covers warehouse medium
   `BatchSilver` and an incomplete MDM-medium run.

## Minimum bounded rehearsal and replacement decision

The recommended route is to reject the proposed old-image cohort, persist the
current six-revision cohort as the release baseline, and retain one canonically
identical earlier cohort as a **control-plane recovery** set. Before calling any
cohort a known-good code rollback, run the bounded contract against immutable
images built after `ee62a968` and `98adb781`. Rehearsing the proposed cohort for
hours before testing its known fail-fast defect has poor value.

If the operator still wants to evaluate this exact cohort, use this order:

1. **Freeze identity before execution.** Capture the six exact task-definition
   JSON documents, immutable digest/source tags, and canonical hashes of the 26
   current ASL definitions. Produce a temporary, unscheduled Standard state
   machine definition by changing only task-definition references to the
   proposed six revisions. This tests the rollback that would actually be
   performed today without overwriting the live 26-machine portfolio.
2. **Run the MDM fail-fast discriminator first.** On
   `edgartools-prod-mdm-medium:138`, execute the same bounded
   `mdm run --entity-type all --limit 5` surface that reproduced the fund
   defect, then execute it a second time against the same bounded candidate set.
   Require both exits to be zero, no duplicate/integrity error, and identical
   entity/relationship semantic counts. Any failure rejects the cohort; do not
   proceed to a long workflow.
3. **Run one fresh bounded end-to-end canary.** Use a new execution name and a
   frozen 1-5-CIK input through bronze/seed, `BatchSilver`, MDM run/backfill,
   export, graph sync/verify, gold refresh, and gold-live verification. Require
   every state and child execution to succeed; inspect `Catch` paths; verify
   output manifests, row/semantic digests, publication watermark, graph parity,
   and a no-change rerun. Do not redrive an older execution because it retains
   the definition frozen at its original start
   (`.scratch/pipeline-resumability/map.md:40-43`).
4. **Cover the two profiles the representative chain does not exercise.** Run
   one bounded warehouse-small utility and one bounded residual-holds command
   on MDM large, followed by the small-profile MDM verification command. Record
   exact task ARNs, log streams, commands, limits, exit codes, duration, peak
   CPU/memory, and output checks.
5. **Persist one immutable result.** Bind the temporary ASL hash, all six task
   revisions/digests, execution and child identities, evidence hashes, and
   attestation into a release/rollback manifest. A representative bounded pass
   can prove these task binaries remain operable with today's orchestration; it
   cannot reconstruct an uncaptured historical 26-state-machine release.

Because the fail-fast MDM test targets a production-reproduced defect in the
immutable proposed image, the expected safe outcome is rejection and selection
of a newer rollback cohort. Until a replacement passes and is persisted, keep
the proposed six revisions and tags protected from cleanup as recovery evidence,
not as a designated known-good release.
