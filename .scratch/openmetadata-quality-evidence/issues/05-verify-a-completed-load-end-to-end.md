# Verify a Completed Load End to End

Type: task
Status: open
Blocked by: 03, 04
Blocks: 06, 07
Labels: wayfinder:task

## Question

Does one safely selected, already captured local load produce complete
Bookkeeping evidence that is admitted, published per load, and confirmed by
exact OpenMetadata readback?

## Checklist

- [ ] Inspect local run and capture state read-only; select a suitable existing
  capture without requesting new provider data.
- [ ] Check shared-server activity and confirm the selected local run is safe
  before executing it.
- [ ] Verify per-unit outcomes are admitted and counted once.
- [ ] Publish its native quality results and read back each exact timestamp,
  status, count and result detail.
- [ ] Confirm identical replay is idempotent and incomplete or failed
  publication remains explicit with nonzero status.
- [ ] Confirm `check` is read-only and record the run reference and evidence.
- [ ] Learning → skill: record `none` or name the skill line changed.
