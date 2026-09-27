---
name: change-journal
description: Plan, validate or deploy Change Journal for an explicit source and feed, including evidence receipts and owner-delegated delivery recovery. Work execution belongs to Bookkeeping and source policy to Rules.
---

# Change Journal

Invoke `$change-journal plan|validate|deploy --source <source> --feed <feed>`.
Each mode requires both identities. Preserve supplied values; resolve unknown
or ambiguous feeds through the shared Bookkeeping descriptor resolver before
dependent work. Read the [contract](../../docs/specs/change-journal.md).

Use `uv run --extra mdm --extra s3` from the intended repository worktree.
Resolve the skill's physical path so relative links refer to that checkout.
The helper uses the same descriptor resolution as Bookkeeping:

```bash
uv run --extra mdm --extra s3 skills/bookkeeping/scripts/resolve_feed.py --source <source> --feed <feed>
```

## Plan

Read the selected source's Rules file and bounded source-owned manifests.
Record exact feed/dataset members, target, Rules digest, input references,
processing versions, producer counts and recovery scope. Planning reads
artifacts and creates only a local plan bundle; it does not connect to a
database, activate Rules or request a provider. Use the actual helper:

```bash
uv run --extra mdm --extra s3 skills/change-journal/scripts/run_mode.py plan \
  --source <source> --feed <feed> --target <target> \
  --input-manifest <uri> --input-sha256 <hash> --output <plan.json>
```

Unsupported required stages remain explicit blockers. A fixture capture is
not proof of a parser, downstream publication, or production feed parity.

## Validate

Use isolated local PostgreSQL 16 Bookkeeping, Rules and journal stores with
restricted runtime connections and separately applied migrations. The helper
requires the exact planned Rules version already proven/approved/active in
those isolated stores; it never creates a person's approval. MDM validation
requires a separate loopback `change_journal_validation_*` database; unset
`MDM_DATABASE_URL` when the target does not need MDM. Configure
`BOOKKEEPING_CLEAN_DATABASE_URL`, `RULES_DATABASE_URL`,
`CHANGE_JOURNAL_DATABASE_URL` and `BOOKKEEPING_MANIFEST_ROOT`.

Run `run_mode.py validate --source <source> --feed <feed> --plan <plan.json>
--output <validation.json> --limit <bound>`. Inspect actual producer counts,
required checks, receipt hashes and zero pending intent. A partial result
returns 3 and cannot qualify deployment. Exercise the affected scope's outage,
lost acknowledgement, stale lease, duplicate/conflicting delivery, input drift,
checkpoint contention/holes and completeness tests. Required acceptance is
`tests/integration/test_change_journal_postgres.py`,
`test_change_journal_acquisition_postgres.py` and
`test_configured_bookkeeping_postgres.py`; missing prerequisites must fail.

## Deploy

Use `run_mode.py deploy --source <source> --feed <feed> --plan <plan.json>
--validation <validation.json> --output <deployment.json> --limit <bound>`.
The helper rejects changed scope, Rules, processing versions, inputs or
incomplete validation. Target Rules must already have the exact approval and
activation; deployment submits configured work through Bookkeeping. Apply
journal migrations only through the separate owner connection with
`edgar-warehouse change-journal init --runtime-role <role>`.

Retain validation stores for durable read-back. When target stores differ,
provide both `BOOKKEEPING_VALIDATION_DATABASE_URL` and
`CHANGE_JOURNAL_VALIDATION_DATABASE_URL` as explicit read connections.
The helper verifies the actual completed root, frozen submission, counts,
checks, backlog and journal receipts; a local report alone is insufficient.

AWS application rollout uses `infra/scripts/deploy-aws-application.sh` only
after all affected feed gates pass. Finish or retain legacy runs on their
original stack and drain their pending intent there. Never import history or
relabel an old event for the fresh journal. Physical retirement is separate;
preserve the archive indefinitely by default.
Fresh connection flags create separate journal task families with a read-only
status default. Existing workflows keep their original task bindings. Select
a fresh task for an approved feed only after full replacement stages qualify.

## Recovery and result

Confirm commands through `edgar-warehouse change-journal --help`. Inspection is
bounded. Receipt verification proves durable envelope delivery; the owning
artifact or MDM verifier proves business effects. `change-journal recover
bookkeeping <run-id> --limit <bound>` delivers committed intent only. MDM
recovery uses `recover mdm <batch-id> --worker <worker>` and the owning fence.
Neither silently executes new provider work or redirects historical backlog.

Report mode, source/feed, exact members, retained bundles/root run, verified
counts, receipts, backlog and remaining gaps. Keep planning, isolated
qualification and live deployment distinct.
