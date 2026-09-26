# Speed up the Company publication payload

Type: task
Status: open
Blocked by: none
Blocks: Phase 2 of the Proving Run (ticket 05) at whole-population scale

## Outcome

A Merge Stage batch of about 1,000 SEC Company records commits in seconds,
not minutes, with the same publication payload and hash as today.

## Evidence (ticket 05, 2026-09-26)

The Proving Run switched on PostgreSQL per-function timing
(`track_functions = 'pl'`) on its disposable database:

| Function | Calls | Self time |
| --- | --- | --- |
| `mdm_v2.company_payload_from_table` (037) | 42 | 1,639 s |
| `mdm_v2.assessment_snapshot` (028) | 21 | 149 s |
| `mdm_v2.commit_batch_core` | 14 | 59 s |
| everything else | | under 20 s each |

Out of 1,796 seconds in `commit_batch_evidence`, 91% went to
`company_payload_from_table`, about 39 seconds per call. It is called by the
`publish_company_authority` trigger on every publication row.

Its loop builds the objects array one element at a time:

```sql
rebuilt := rebuilt || jsonb_build_array(item);
```

Each append copies the whole array built so far, so one call costs time in
proportion to the square of the number of objects. It also runs one lookup
per Company object. A batch of about 960 records took 3–6 minutes. The
whole SEC population, 77 batches, would take about four to eight hours.

## Checklist

- [ ] `/gof-refactor-reviewer` on migration 037's publication functions.
- [ ] A failing test first: a populated store, a batch of about 1,000
  Companies, and a time bound. The payload and hash must equal what the
  current function produces for the same batch.
- [ ] A new migration restates the function whole (not edited as text).
  It builds the array with one `jsonb_agg ... ORDER BY ordinality`,
  joins `mdm_v2.company` and `mdm_v2.company_alias` once, and keeps the
  refusal "Company publication has no dated authority".
- [ ] Prove it on PostgreSQL 16 against a store populated before the
  migration, and rerun ticket 05's chunk 1 for the new timing.
- [ ] Look at `assessment_snapshot` (149 s over 21 calls) in the same way.
  Change it only if the evidence holds up.
