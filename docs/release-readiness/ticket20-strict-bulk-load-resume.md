# Ticket 20 strict bulk-load resume (P0 / P1 / P3)

## P3 operator rule (read first)

**Do not redrive a failed `bronze_seed_silver_gold` Step Functions execution after
deploying a new warehouse image or task definition.** AWS redrive pins the task
definition revision that last ran; a redrive will **not** pick up click fixes,
resume markers, or other image changes.

Always:

1. Deploy the new image / task definition (fresh registration).
2. Start a **new** execution name.
3. Point `candidate_batches_key` at **remaining** batches when using P0.
4. Keep the same frozen `candidate_manifest_key` (and watermark / fingerprint).

Redrive is only appropriate for identical image/revision transient blips (for
example a one-off network flap with no code or image change). Prefer a new
execution for Ticket 20.

## Freeze layout

Under the freeze prefix (parent of `candidate_manifest.json`):

```text
{freeze}/
  candidate_manifest.json
  candidate_batches.jsonl
  candidate_batches_remaining.jsonl   # optional, operator-generated
  batch_done/{batch_identity}.json    # P0: batch fully completed
  accession_done/{accession}.json     # P1: single candidate terminal
```

`batch_identity` = first 16 hex chars of
`sha256(",".join(sorted(str(cik) for cik in batch)))`.

## P0 — batch resume

After a successful strict `bootstrap-batch`, the runtime writes
`batch_done/{batch_identity}.json`.

Build remaining map input:

```bash
uv run python -m edgar_warehouse.scripts.build_remaining_release_batches \
  --candidate-batches s3://…/{freeze}/candidate_batches.jsonl \
  --output s3://…/{freeze}/candidate_batches_remaining.jsonl
```

Start Step Functions with:

| Field | Value |
| --- | --- |
| `release_mode` | `true` |
| `candidate_manifest_key` | original freeze manifest key |
| `candidate_batches_key` | **remaining** batches key |
| attestations | same five named roles |

## P1 — accession resume (mid-batch)

When a candidate reaches a **terminal** ledger status
(`applicable_loaded` / `not_applicable` / `superseded`), the runtime writes
`accession_done/{accession}.json` bound to:

- inventory fingerprint
- candidate fingerprint
- evidence fingerprint

On a later run of the **same freeze**, those accessions are loaded first and
**skipped** for artifact fetch + Branch B parse. Explicit `--force` with a
repair manifest still re-processes named accessions (markers ignored for those
rows).

## P2 — progress visibility

Artifact loops emit `filing_artifact_pipeline_progress` every N accessions
(`WAREHOUSE_ARTIFACT_PROGRESS_EVERY`, default `100`).

## End-to-end resume checklist

1. Confirm root cause fixed in a **new** image; deploy task defs (do not redrive).
2. `build_remaining_release_batches` → remaining JSONL (P0).
3. New SF execution: same manifest key, remaining batches key, five attestations.
4. Watch CloudWatch for:
   - `release_accession_resume_loaded` (P1 skips)
   - `filing_artifact_pipeline_progress` (P2)
   - `release_batch_done_marker_written` (P0 batch complete)
5. After map success: `reconcile-relationship-release` continues as today.

## What resume is *not*

- Not `artifact_policy=skip` (invalid for Ticket 20 GO).
- Not “skip SEC forever without markers” — cache hits still apply; markers prove
  **terminal ledger** outcomes for the freeze fingerprint.
- Not redrive-after-image-change (P3).
