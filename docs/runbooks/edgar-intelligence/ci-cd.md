# Edgar Intelligence runbook: CI/CD

Promoting tested configuration to an environment. Index: [README](README.md).

## Configuration promotion

Final means a fixed, tested and approved version. Git retains the authoring
files; the destination Rules database retains execution authority. Approval is
recorded evidence on a version; activation selects that version in an environment.
Copying files into a folder named final establishes neither.

| Stage | Owner and completion evidence |
| --- | --- |
| Author | data-onboarding creates a source; refining-rules changes an existing source/domain. The exact configuration and generated documents are versioned. |
| Check | Validate only changed documents locally; CI checks the full Rules tree ([LOAD](../../../skills/data-onboarding/LOAD.md)). |
| Deploy | The rules files ship with the image. `rules register` registers the merge rules and Dataset Contracts in the destination's MDM. |
| Operate | data-operations checks the completed delivery, capacity and dependencies, then submits/resumes and verifies through Bookkeeping and Change Journal. |

Keep a release record referencing the source configuration, dataset/matching/
merge versions, RDM/shared-input pins, runtime, test artifacts and approval.
Environment connection settings, credentials and operational state remain private
and separate from that record. A release record is an index into existing
evidence, not a second Rules database or a new status store.

Promote the same content and applicable evidence to the destination. Recheck
connectivity, roles, registered worker capabilities and delivery/dependency
availability there. A new environment alone does not require repeating unchanged
business-rule qualification. Exact hashes, retrievable genuine artifacts and
the supported destination lifecycle must still validate. An older source's
approval does not approve a changed policy, and a schema migration is separate
from configuration promotion.

The rules files ship with the code; `rules register` registers them in a destination's MDM.
If required evidence cannot be represented or a consumer still requires download
producer steps, report that runtime gap; do not forge proof, register through test
helpers or bypass activation. Keep source-specific readiness status in its
operational record. Publishing this skill does not resolve runtime gaps or
deploy any Rules version.

The skill's maintained source is `skills/data-operations/` in the repository;
the data-platform package ships it to the installed agent skill folders. A
source runbook references the release and its active environment/run IDs.
