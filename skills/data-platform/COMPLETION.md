# Guide work from current state to completion

Use this procedure for a draft without proof, an approved release awaiting
deployment, missing native integration, or an operator asking what remains.
Keep current counts, versions and engine-specific findings in the task/source
operational record. Read them live; this shared guide carries no readiness
snapshot for a particular source.

## 1. Explain the current state

Resolve the requested source/domain, selected engine, environment and intended
outcome from the task and existing authorization. Inspect the operational
record, actual running build, native store migrations, Rules registrations,
worker/verifier capabilities, retained delivery and existing runs/leases.
For installed execution, run `edgar-warehouse doctor` from that package outside
the checkout so its shipped references and named commands are checked too.
Keep each selected engine separate. A command inventory or working connection
does not establish the native pipeline path.

Show a compact table with one row per target: native integration, selected
source/merge versions, cross-reference mapping/lookup readiness, proof,
approval, activation, delivery/run verification and next action. Explain what
the observations mean:

| Observation | Meaning and next action |
|---|---|
| Draft, no proof | Qualification has not been recorded. Find inputs and run the owning skill's test mode. |
| Recorded failed proof | Explain the failed checks, fix and rerun; save a new version if configuration changes. Follow the shared approval procedure for any permitted overrule. |
| Passing proof, no approval | The version is proven. Show its changes and evidence for exact-version approval. |
| Matching approval, inactive | The release is approved; deploy/activate under the applicable operator authorization. |
| Active, delivery not verified | Registration is live. Run or resume processing and independent verification. |
| Storage-helper fixtures pass, native path refuses | Storage qualification exists; the requested native integration is still an engineering task. |
| Cross-references carried, native mapping/lookup unverified | Complete the MDM cross-reference step before claiming those records lookup-ready. |
| Delivery verified and unchanged repeat does no work | The declared retained delivery is complete. Report that scope separately from full provider history. |

**Done:** every target has an evidence-backed state, a plain explanation and
an actionable next step. Maintain the remaining steps as a checklist in the
existing task record; evidence references point to the owning ledgers/artifacts.

## 2. Carry native integration gaps through their owner

Use [data-operations](../data-operations/SKILL.md#apply-store-ddl) to check each
store and the actual configured caller path. Name the refused operation,
affected engine, owning code and proof needed. Preserve the selected engine.

For authorized engineering, continue through [MDM engineering](../mdm-engineering/SKILL.md)
for MDM adapters/merge integration, [Bookkeeping](../bookkeeping/SKILL.md) and
[Change Journal](../change-journal/SKILL.md) for their protocols, and this skill
for configured pipeline coordination. Data-operations coordinates the remaining
store owners and deployment. Apply the repository's design review and ownership
rules; implement and qualify missing native operations before returning here.
Keep adapter implementation in its owning skill and computation shared.

**Done:** the selected engine's native registration, reads, worker commits,
verification and publication path pass their owning qualification. Fixture
persistence alone leaves this step open. If implementation needs a genuinely
new scope decision or is unavailable, record that concrete dependency and its
next engineering action while continuing supported targets and evidence work.

## 3. Find the inputs and exact version

Inspect registered versions and the authoring configuration. Resolve existing
proofs, release records, captured-file manifests and acquisition receipts from
the source's operational record, configured artifact roots and retained run
references. Verify retrievability, hashes, configuration digest and declared
input/dependency scope. Reuse matching genuine evidence; a new environment
alone does not require repeating unchanged business-rule qualification.

For a new proof, start from the draft and available captures. Follow
[onboarding test mode](../data-onboarding/SKILL.md#test-run-it-on-real-captured-files-and-record-the-result)
or [refining-rules](../refining-rules/SKILL.md) for changed rules. Save a new
version when the configuration changes; retain the original pins of existing
runs. Keep the exact source/merge versions and runtime fixed for qualification.
Check that an MDM source declares the acquisition/registration authority its
native handoff requires. A missing declaration goes through onboarding or
refining-rules as a configuration change and receives a new qualified version.

**Done:** the version and hash-verified inputs are identified, or a precise
missing delivery/artifact is recorded. Ask for an artifact path only after
checking the task's known references. The agent generates missing proof from
observed results; the operator need not supply a pre-existing final proof.
If files require acquisition, follow the existing AWS acquisition handoff and
provider authorization instead of inventing receipts. Continue independent
mapping/merge qualification when its retained inputs are ready.

## 4. Map and qualify cross-references in MDM

Classify identity identifiers, lookup-only cross-references and reference-code
crosswalks using [data-modeling](../data-modeling/SKILL.md#3-identity-or-cross-reference).
Source-to-master bindings and cross-reference resolution live in MDM; versioned
code-set crosswalks live in RDM. Follow
[MDM cross-reference completion](../mdm-engineering/SKILL.md#cross-reference-completion)
for the authoritative mapping, native lookup and engine-specific proof.

**Done:** every carried cross-reference has its declared mapping/format and
verified source-record/master/provenance lookup on the selected engine.
Shared lookup values preserve record multiplicity, unbound records stay
unbound, and approved merges resolve to the canonical master. Include
correction/retirement and unchanged replay in the owning qualification.
Record evidence when no cross-references apply to the input scope. A missing
native cross-reference capability remains an explicit integration task.

## 5. Run qualification and produce the proof

Execute the owning test mode on the exact captured inputs in its qualification
environment. Verify counts and dispositions, matching, field/profile selection,
relationships, recovery and unchanged replay as applicable. Bind the report to
the selected configuration and actual files read, including shared inputs.
Use the documented qualification registration; test authority remains test-only.

Write the private proof JSON from the run's measured results. The owning test
mode defines `digest`, `batch_hash`, `passed`, `evidence` and `note`; compute the
hashes and retain retrievable report references. A test run over
files already captured switches on the source's pipes; its live acquisition is
switched on apart, with a version whose proof also holds every declared feed's
genuine manifest, expected and verified producer counts and successful checks
(operator, 2026-10-19). Unit tests, adapter fixtures and invented records
qualify implementation only.

**Done:** the exact version has a genuine passing proof, or a recorded failing
result with its failed checks and repair action.

## 6. Record the proof and explain what is ready

Use the supported lifecycle with the configured private Rules runtime:

```bash
edgar-warehouse rules record-proof --source <name> --version <version> \
  --proof-uri <artifact-uri> --proof-sha256 <artifact-hash>
edgar-warehouse rules pending
```

Use `--merge <name>` for the merge version. The agent resolves and supplies the
artifact hashes; the operator reviews the business changes and measured results.
Check the recorded proof matches the selected version. Explain any refusal and
repair its actual cause, such as mismatched content or incomplete acquisition.

**Done:** the proof is recorded; a passing version is proven and listed for
approval. A failed result retains its status and repair action, with any
permitted overrule handled by the shared approval procedure. Explain that
an approved release is the fixed tested content plus its recorded approval;
activation selects it in an environment. A folder name or a manually changed
status supplies neither evidence nor approval.

## 7. Obtain or reuse exact-version approval

Follow [APPROVE](../data-onboarding/APPROVE.md). Show the descriptive version
name, what changes, the measured results and any remaining deployment limits.
Use genuine applicable approval already given for the same version and
evidence; a version whose test run passed is approved under the operator's
standing approval (APPROVE, step 3). Ask only for a failing run's overrule,
a new kind of decision or a switch-on, and record the operator's actual
words through the supported command. A deployment instruction
does not invent approval for different content or supply a missing test run.

**Done:** the recorded approval names this version and its current proof.
While approval is pending, finish independent preparation; leave the dependent
approval/activation step pending. A changed proof requires the lifecycle's
evidence recheck rather than carrying an older approval silently forward.

## 8. Deploy and activate

Follow [configuration promotion](../data-operations/RUNBOOK.md#configuration-promotion)
for the destination and the shared approval procedure's switch-on steps.
Reuse authorization already given for this action and exact release; resolve
only a genuinely missing authorization. Deploy the approved merge policy before
its dependent source versions. Preserve required RDM/shared-input versions.

**Done:** destination `rules status` shows the intended versions active and
the native MDM registrations/handoff receipts match. Record the destination
readback. A source activation refusal remains a failed step with its actual
cause, not a reason to bypass the lifecycle or fabricate a successful receipt.

## 9. Operate, verify and close the loop

Continue [Parse](SKILL.md#2-parse) and [Master](SKILL.md#3-master), coordinated
by [data-operations](../data-operations/SKILL.md). Resume existing work under
its frozen pins, process dependencies in order, use the separate verifier and
verify required consumer/Journal delivery and native MDM cross-reference
lookups against the committed source/master state. Account for every file and every
accepted, waiting or rejected record in the declared retained delivery.

**Done:** native runs and their declared units are verified, destination
publication receipts hold, retained checkpoints agree, and an unchanged repeat
selects zero files and starts no mastering work. Re-read the task checklist.
Report completed targets and scope, counts, evidence references and any open
target's exact prerequisite, owner and next executable step or code change.
Guide the operator through that next step; a missing-proof label or owner name
alone is not a completion plan.
