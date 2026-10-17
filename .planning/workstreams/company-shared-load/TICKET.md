# Deploy Company configuration and load shared PostgreSQL

Status: blocked before submission. Operator: "how do i deploy approved config, rules and merge policy for company can you run company".

## Checklist

- [x] Establish isolated worktree and refresh main without changing protected checkout. Verified `codex/company-shared-load-20261017` at `272f60a0`, zero divergence after successful fetch. 2026-10-17 09:15 ET.
- [x] Check exact shared lifecycle state. Company and platform merge policy each have one draft, no recorded proof and no recorded approval. Company canonical body matches committed configuration; saved merge policy canonical body differs. Shared MDM has zero Company masters, datasets and policies; Bookkeeping has zero runs. Read-only aggregate queries. 2026-10-17 09:15 ET.
- [x] Attempt supported activation of existing versions using the separate governance connection. Both refused `Only a proven version can activate`. Transactions rolled back; post-attempt active version count remains zero. Real Rules resolver also refuses Company execution. 2026-10-17 09:15 ET.
- [x] Identify remaining runtime mismatch. Validated committed targets and compared their step names with declared acquisition producers. `mastering` and `mdm` lack all three required producers (`capture`, `sec_company`, `sec_company_filing`); `capture` lacks the latter two. `Bookkeeping.start` applies these requirements whenever the source has acquisition configuration, including consumer targets. This code inspection is a blocker analysis, not a claim that an activated end-to-end run was tested. 2026-10-17 09:15 ET.
- [x] Record the operator's processing boundary in `docs/specs/source-readiness.md`: AWS owns downloading; local processing requires genuine completed-delivery evidence, reconciled inventory and receipt/hash checks, freezes those references and never triggers acquisition. Verified against the operator's clarification and current `start`/resume checks; documentation only. 2026-10-17 12:46 ET.
- [ ] Complete genuine retained-capture qualification and consumer authority support. Preserve acquisition checks for acquisition; qualify local processing against real retained evidence. Reuse existing source-readiness design; do not manufacture producer receipts, approvals or a frozen active envelope.
- [ ] Deploy the intended exact merge policy and Company source with their real evidence and existing approval provenance. Reconcile policy content first; do not relabel the older saved policy as approved current configuration.
- [ ] Process the entire retained capture, with whole-population Name Frequency, pinned catalog/references, workers, independent verifiers and Journal recording. Finalize and reconcile all outcomes.
- [ ] Prove unchanged repeat selects zero files and starts no new mastering run.
- [x] Learning → skill: none. Existing data-platform Source readiness requirements already distinguish local capture qualification from AWS capture and forbid fabricated lifecycle evidence. 2026-10-17 09:15 ET.

## How deployment works

Versioned files in Git are the authoring configuration. The shared Rules database is the execution authority. Saving a file is not approval, activation or a data load.

1. Compare intended configuration with the exact version that was tested and approved. Save a missing exact version through `rules save`; never change an immutable version's content.
2. Record its genuine test evidence through `rules record-proof`. Reuse a historical approval only when it applies to that exact version and evidence; retain the operator's actual words, never invent an approval. Configuration-level identifier approvals do not replace the Rules version lifecycle.
3. With private governance connections loaded, activate the merge policy, then the Company source. These are existing supported commands, currently refused for the seeded drafts:

   ```bash
   edgar-warehouse rules activate --merge platform --version "$MERGE_VERSION"
   edgar-warehouse rules activate --source sec.submissions.company --version "$COMPANY_VERSION"
   ```

4. Verify both versions are active using `rules status --merge platform` and `rules status --source sec.submissions.company`.
5. Use the source's `mastering` path over the full retained delivery. The current separate `mdm prepare-clean-company` preparer and consumer/acquisition mismatch remain implementation gaps in the agreed common-command target. After submission works, execute and independently verify the declared steps in order: main/keys/catalog/census (`source.read`), combine (`source.combine`), records (`mdm.prepare`), merge (`mdm.merge`), processed (`journal.record`), then `bookkeeping finalize`. Reconcile every bundle, not just one worker invocation.

Private environment files are under the existing `codex-local-lab` environment directory. Use governance duties for deployment, worker duties for work and verifier duties for verification. No values from those files belong in reports.

## Result

No load was submitted or source activated. No shared data, schema, existing configuration version or approval was changed. No provider request, AWS operation, silver load or server maintenance occurred. Approval alone cannot resolve the missing runtime support.
