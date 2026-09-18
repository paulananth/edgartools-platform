# Clean MDM delivery record

Status: Q1–Q16 accepted; local shared-core implementation in progress.
No hosted qualification or consumer cutover has occurred.

Inspected code: `b1babd8bbd0e04044fcacbbab822d480c97c01bc`, fetched from
`origin/main` on 2026-09-17. No production state is asserted by this record.

## Read in delivery order

1. [Domain model](domain-model.md) and [pipeline inventory](pipeline-inventory.md).
2. [Source evidence](source-evidence.md), [Merge Stage](merge-stage.md), and
   [journal/recovery](recovery.md) contracts.
3. [Acceptance, target qualification, and cutover](acceptance.md).
4. [Evidence report](evidence.md), which distinguishes completed checks from targets.

The [Wayfinder policy ticket](../../../.scratch/clean-mdm/issues/01-set-merge-stage-policy.md)
records the resolved policy gate. The PostgreSQL foundation and shared merge
library are implemented and under acceptance testing. Source pipeline and hosted
consumer integrations remain incomplete; see the [evidence report](evidence.md).

The [vendor comparison](../../research/clean-mdm-vendor-merge-rules-2026-09-17.md)
revises the initial match-threshold and survivor-ID proposals and supplies the
current interview questions. Research completion is not policy acceptance.

## Existing decisions carried forward

- [Independent domain publication authority](../../adr/0010-independent-source-grained-mdm-enrichment-consumers.md).
- [Commit evidence bound to its originating run](../../adr/0007-bind-mdm-commit-evidence-to-originating-run.md).
- [Run, transaction, and artifact-transition ownership](../../../.scratch/mdm-enrichment-program/issues/08-set-run-transaction-and-artifact-transition-authority.md).
- [Existing SEC Bronze migration is deferred](../../../.scratch/mdm-enrichment-program/issues/09-defer-existing-sec-bronze-migration.md).
- [Approved GLEIF publication and mapping families](../../../.scratch/mdm-enrichment-program/source-file-pipeline-catalog.md).

The old separate-domain identity model remains a description of the running
system. This effort is the explicitly requested migration to shared identities;
it does not retroactively mark the old model as an error or grant unimplemented
enrichment consumers release approval.

## Q16 resolution — 2026-09-18

The user accepted starting the offline build with unqualified automatic rules
disabled. This supersedes earlier pre-implementation calibration timing above.
Q1–Q16 are accepted; numeric calibration and versioned policy evidence are
mandatory before each automatic rule activation. Implementation is authorized;
production activation still requires all local and hosted acceptance gates.
