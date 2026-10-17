# Ongoing data operations skill: existing options and fit

Research checked: 2026-10-17 13:03 ET. This is a documentation comparison,
not installed-tool qualification or proof that a source can run.

## Recommendation

Add a repository-owned **data-operations** skill for recurring load management.
Reuse the existing data-platform, Bookkeeping and Change Journal contracts.
Borrow a clear runbook structure from existing skills; do not install another
scheduler, service or workflow engine to obtain that structure.

This recommendation is an inference from the examined skill texts below and
the repository contracts. None of those examined texts supplies this platform's
combination of verified captured deliveries, approved frozen inputs, shared
resource sizing, independent verification and producer-owned journal recovery.
That is a bounded finding, not a claim that no suitable skill exists anywhere.

## Search scope and source quality

Searched the public skills.sh directory and primary GitHub sources for runbooks,
capacity planning, data engineering, freshness and failure diagnosis. Two actual
skills CLI searches completed for `data pipeline operations` and `runbook`, using
the preexisting cached CLI after the offline npx lookup failed with ENOTCACHED.
Read six actual skill texts: two from Anthropic, two from Astronomer, one from
Goldsky and one community data-engineering skill. Directory descriptions alone
were not capability proof.

Anthropic's repository is published under `anthropics`; Astronomer's README
identifies Astronomer as its author and describes its Airflow tooling. These are
first-party sources for their own skills, not endorsements of our integration.
Goldsky publishes its agent under `goldsky-io` for its own pipeline product.
The community skill is independently maintained and is not an official
Anthropic, Astronomer or Goldsky implementation. [Anthropic repository](https://github.com/anthropics/knowledge-work-plugins),
[Astronomer README](https://github.com/astronomer/agents/blob/main/README.md),
[Goldsky repository](https://github.com/goldsky-io/goldsky-agent),
[community source](https://github.com/alirezarezvani/claude-skills/blob/main/engineering-team/skills/senior-data-engineer/SKILL.md).

The directory displayed 2.9K installs for Anthropic runbook and 2.8K for
capacity-plan. These are directory-reported snapshots, unverified as unique
users, successful executions or operational quality. Its pages displayed
different star totals for the same repository; no reputation ranking is based
on those totals. [Runbook listing](https://skills.sh/anthropics/knowledge-work-plugins/runbook),
[capacity-plan listing](https://skills.sh/anthropics/knowledge-work-plugins/capacity-plan).

Some directory pages for Astronomer freshness/debugging were inaccessible;
their skill sources were readable. A dtsong candidate README returned 404 and
was excluded rather than assessed from its listing. No exhaustive marketplace
audit, candidate-skill installation, candidate-script execution or provider data
request occurred; external access was limited to software research.

## Examined skills

| Existing skill | Actual capability in examined text | Fit to this request |
| --- | --- | --- |
| Anthropic `runbook` | Documents recurring procedures, prerequisites, expected results, verification, troubleshooting, rollback and run history. Optional knowledge-base/ITSM integration. | Useful documentation shape. Its text does not implement load selection, resource measurement, Bookkeeping coordination or Journal acknowledgements. |
| Anthropic `capacity-plan` | Models team headcount, roles, hours, project demand, budget and hiring scenarios. | The word capacity refers to people. It does not measure CPU, memory, disk, database pressure or select safe loader batch/concurrency settings. |
| Astronomer `checking-freshness` | Queries timestamps and recent row activity, then investigates the corresponding Airflow pipeline. | Useful stale-data investigation concept. Table timestamps do not establish a complete local delivery or unchanged input identity. Its default age categories are not this platform's source-specific readiness policy. |
| Astronomer `debugging-dags` | Inspects actual run/task failures and logs; compares upstream health, volume, recent changes and dependency versions; reports cause, impact and recovery. | Useful diagnosis sequence. Its commands and run recovery belong to Airflow; substituting them would introduce another control system. |
| Goldsky `turbo-operations` | Reference for pipeline lifecycle, streaming versus job behavior, logs, inspection and checkpoint consequences. Warns that renaming a pipeline or source resets checkpoints. | Closest examined lifecycle reference, but tied to Goldsky. Its batch job mode cannot pause/resume/restart; delete/reapply destroys checkpoints. Neither behavior is our frozen-resume contract. |
| Community `senior-data-engineer` | Broad pipeline architecture, quality validation, performance optimization and tooling references. Its quick start generates orchestration configuration. | Primarily construction and optimization guidance; the examined entry text does not define our recurring delivery/lease/receipt protocol. |

Sources for the table:
[Anthropic runbook](https://github.com/anthropics/knowledge-work-plugins/blob/main/operations/skills/runbook/SKILL.md),
[Anthropic capacity-plan](https://github.com/anthropics/knowledge-work-plugins/blob/main/operations/skills/capacity-plan/SKILL.md),
[Astronomer checking-freshness](https://github.com/astronomer/agents/blob/main/skills/checking-freshness/SKILL.md),
[Astronomer debugging-dags](https://github.com/astronomer/agents/blob/main/skills/debugging-dags/SKILL.md),
[Goldsky turbo-operations](https://github.com/goldsky-io/goldsky-agent/blob/main/skills/turbo-operations/SKILL.md),
[community senior-data-engineer](https://github.com/alirezarezvani/claude-skills/blob/main/engineering-team/skills/senior-data-engineer/SKILL.md).

## What the coordinating skill should own

The following is a proposed division of responsibility, based on the user’s
requirements and the repository's existing contracts, not external features.

| Recurring decision | Required behavior | Existing owner retained |
| --- | --- | --- |
| Is a delivery available? | Consume AWS capture/completion evidence; authenticate expected members, hashes and completeness locally. Missing evidence waits with a reason. Never initiate acquisition. | Acquisition producer owns its completion evidence; processing validates it. |
| What changed? | Enumerate the complete delivery, compare stable source/member identity, content and relevant processing versions. Explain new, unchanged, changed, missing and ambiguous members. | Configured selection and Change Journal processing identity. |
| Can this load run? | Check installed commands, active approved versions, required dependencies and real worker support; distinguish a structural sequence check from runtime readiness. | Rules and data-platform. |
| How much can run? | Inspect actual available CPU/memory/disk and shared database/worker pressure, compare measured workload history, then choose supported batch and concurrency controls conservatively. | Existing worker controls, Bookkeeping leases and destination enforcement. |
| What is already running? | Inspect before submitting; continue the existing run and frozen inputs, avoiding competing work for the same delivery. | Bookkeeping run/worklist/lease/checkpoint state. |
| Did it finish? | Reconcile input scope and accepted/waiting/rejected outcomes, destination verification and durable producer event receipts; pending delivery is not success. | Separate verifiers, producer outboxes and Change Journal. |
| What needs changing? | Route schema/meaning/rule drift to profiling, onboarding or rule refinement; a routine manager must not invent new mappings or matching policies. | Existing specialist skills. |

Contract evidence:
[data-platform](../../skills/data-platform/SKILL.md),
[Bookkeeping](../../skills/bookkeeping/SKILL.md),
[Change Journal](../../skills/change-journal/SKILL.md),
[source readiness](../specs/source-readiness.md),
[sequencing check](../specs/source-sequencing.md).

## File changes and names

A filename is a locator, not sufficient evidence of a new business source or
changed data. The skill should detect a moved/renamed file using authenticated
delivery membership, stable configured identity and matching content evidence.
Equal bytes alone cannot establish that two different logical members are the
same member. A same-name file with different bytes must be detected as changed.

Record the observation and use the supported identity protocol. Do not rewrite
historical events, silently change source identity or promise rename deduplication
unless the runtime actually supports it. Unknown naming patterns, missing
members and schema changes are reasons to investigate the affected delivery;
independent sources should remain runnable.

Rules or reference-input changes can require reconsideration even when file
bytes are unchanged. Resume retains the original versions; new work uses the
new approved versions. This is already the agreed
[source-readiness contract](../specs/source-readiness.md), with implementation
gaps explicitly separated from the design.

## Sizing and evidence limits

Resource sizing is not a source-size refusal. Reduce active concurrency or
partition work under supported controls while retaining the whole available
delivery as the obligation. Never silently sample, discard rows or impose a
new permanent source ceiling. If no supported batching/concurrency control or
resource observation exists, report that implementation gap rather than invent
a CLI flag or claim automatic scaling.

Start from recent measured evidence when comparable; otherwise use an explicitly
bounded pilot and retain its throughput, peak resources, failures and competing
load. Estimates and measurements must be labeled separately. This paragraph is
an implementation recommendation, not a claim those observations are collected
automatically today. A skill supplies operating judgment; database constraints,
leases/fences, immutable manifests and verifiers remain authoritative.

## Result

Use **data-operations** for the ongoing agent role; a runbook is one artifact it
maintains. Existing third-party skills supply useful documentation and diagnosis
ideas, while platform-specific coordination should remain next to the engine
contracts it must obey. Creating instructions does not make an unqualified
source runnable or close missing capture-to-processing runtime enforcement.
