# The Set Aside table

Status: open
Type: task
Owner: claude (map decisions 10, 14)

The finish writes `silver.set_aside`: one row per identifier of a record a classification rule held back by decision
(`classification_deferred`, `classification_entity_undetermined`), keyed as Gold's links resolve (namespace, value), with the
feed, the reason and the Probable Kind. The mirror carries it; no field of the record goes with it.

## Checklist

- [ ] GoF consult on `edgar_warehouse/mastering/links.py` (the finish) and the identifier normalizers
- [ ] The table's spec, registered at init like `master_binding`; its identifiers normalized by the contract's own formats
- [ ] The finish builds it as a snapshot beside `master_binding`; a test fails on today's code
- [ ] On the exposure list and in `sources/managed-mirror.yaml`; the mirror's `alter` adds it (approval in HOSTED-MIRRORING)
- [ ] Proved on the hosted store's held-back records (counts by feed and reason)
- [ ] `/code-review`
- [ ] Learning → skill
