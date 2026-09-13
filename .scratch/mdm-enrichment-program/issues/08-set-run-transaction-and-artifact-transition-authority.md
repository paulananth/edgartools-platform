# Set run, transaction, and artifact-transition authority

Type: grilling
Status: resolved
Blocked by: 07

## Question

Which existing authority owns the durable Root Run, what commits atomically for
one consumer batch, and how does the platform retain exact source bytes when
Bronze becomes temporary staging?

## Answer

Bookkeeping `pipeline_run` owns the durable Root Run and its operational status,
timing, arguments, and verification. The Change Ledger owns the append-only
source and processing decisions, attempts, transitions, outcomes, and reasons.
MDM Commit Evidence owns the entity-change and relationship-version facts. One
shared `run_id` joins these records; no second control schema is introduced.

One bounded consumer batch atomically commits its accepted Change Ledger
decision, historical source assertions, current MDM projection, MDM Commit
Evidence, and Consumer Checkpoint. Failure rolls back the complete batch and
leaves the prior current state and checkpoint active. Bookkeeping observes the
result but cannot authorize a partial business commit. Independent batches may
commit separately; the coordinated Release 1 gate waits for all mandatory
consumers.

The Change Ledger tracks both kinds of transition:

- logical transitions through source capture, normalized evidence, MDM,
  Snowflake, and graph publication; and
- physical transitions through S3 locations and storage classes.

Bronze is a temporary landing stage in the target architecture. After hash,
inventory, and read-back verification, the exact source bytes move to a
low-cost immutable Source Artifact Archive. The Change Ledger records the
temporary object, verified archive object, storage class, transition time,
checksums, and later storage-class transitions. A downstream stage starts only
from a ledger-authorized and verified predecessor. S3 listings and Bookkeeping
status never authorize processing.

This target applies only to the new enrichment pipelines in Release 1. Existing
SEC acquisition pipelines continue to follow ADR 0006 and retain their durable
Bronze Artifact behavior. They may move to temporary Bronze only through a
separate future migration with fresh parity, replay, recovery, retention, cost,
and production rollout evidence. Shared foundation work must not silently alter
the existing SEC storage contract.

Archive restore is not an operational replay or disaster-recovery dependency.
The product needs the most recent authoritative state, not a historical source
snapshot. Recovery therefore creates a ledger-authorized request for the newest
complete Source Publication and rebuilds current state from that publication.
It never waits for the Source Artifact Archive. If the new baseline cannot prove
continuity with the former Ledger Epoch, the ledger records a new baseline and
does not claim historical continuity. Frozen offline fixtures, not production
archive restores, provide deterministic parser and transition tests.

The Source Artifact Archive retains only the latest verified complete
publication for each enrichment publication family. Once a replacement is
verified complete and accepted, the retention operator may delete the
superseded source bytes through an authorized Change Ledger transition. The
source manifest, hashes, publication lineage, MDM Commit Evidence, and exact
deletion record remain permanent. S3 lifecycle age alone cannot authorize the
deletion, and a partial or unverified replacement cannot supersede the retained
complete publication.

Daily and recovery delta bytes do not enter the Source Artifact Archive. They
remain in the Temporary Bronze Stage until every consumer that declares the
delta family as required has committed its Consumer Checkpoint and all required
Snowflake and graph verification has passed. The retention operator then
deletes the exact temporary object through the Change Ledger. A failed,
deferred, or unverified consumer keeps the bytes available for retry. The
manifest, raw hash, transition lineage, terminal record dispositions, MDM
Commit Evidence, and deletion record remain permanent.

"Never looking back" applies to stored source bytes, not to the platform's
explanation of current state. Normalized Source Evidence, Change Ledger and
Bookkeeping history, stewardship decisions, temporal MDM history, manifests,
hashes, lineage, MDM Commit Evidence, and deletion records remain permanent.
Deleting source bytes must not delete, rewrite, or detach any of those records.

Accepted by the user during the 2026-09-13 Wayfinder session.
