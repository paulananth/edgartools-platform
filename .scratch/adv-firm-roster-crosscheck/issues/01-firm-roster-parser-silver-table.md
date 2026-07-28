# 01 — Firm Roster parser + silver table + `ShardedSilverReader` registration

**What to build:** A new silver-layer parser reading the Firm Roster CSV zip archives
(`ia<date>.zip` / `ia<date>-exempt.zip`), mirroring `adv_bulk_ingest.py`'s existing
dataclass-based shape. It produces rows keyed by (`adviser_crd_number`, `dataset_period`)
carrying the ~8 documented aggregate private-fund columns (private-fund flag, 7B(1)/7B(2)
counts, hedge-fund count, total gross assets of private funds, etc.) plus the standard
`source_dataset_period`/`source_sha256` provenance columns every other ADV silver table
carries. Writes to a new `sec_adv_firm_roster` silver table with a `ProtectedTablePolicy`
entry keyed on `(adviser_crd_number, dataset_period)`, matching `sec_adv_private_fund`'s
idempotency-protection pattern (SEC data is additive/immutable once captured — see
CLAUDE.md's "SEC data idempotency" doctrine). The remaining ~440/163 undocumented columns
are not parsed — narrow scope only, per the spec's Out of Scope.

Register `sec_adv_firm_roster` in `ShardedSilverReader._TABLES`
(`silver_support/sharded_reader.py`) in this same change — CLAUDE.md documents a real,
previously-shipped bug (the INSTITUTIONAL_HOLDS/EMPLOYED_BY 5-whys) where a new silver
table was populated correctly but omitted from this allowlist, causing MDM's cross-shard
reader to silently treat it as "missing." Write the registration regression test *before*
adding the entry, confirm it fails, then add the entry and confirm it passes — following
`test_sharded_silver_reader_exposes_thirteenf_filing_and_employment_event`'s exact
precedent.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] Parser unit tests (mirroring `tests/application/test_adv_bulk_ingest.py`'s shape)
      feed a real or minimal synthetic Firm Roster CSV zip through the parser and assert
      on the returned dataclass rows — no network, no Snowflake, no silver database.
- [ ] Silver write + idempotency integration tests run against a real
      `SilverDatabase`-backed DuckDB file (not a hand-rolled stub — see CLAUDE.md's
      "Manifest-pipeline ownership + cursor-syntax incident" entry on why a stub can
      silently drift from the real schema), covering the CRD/`dataset_period` primary key
      and that re-ingesting the same archive is a no-op.
- [ ] A `ShardedSilverReader` registration regression test is written first, confirmed to
      fail against the current `_TABLES` list, then passes once `sec_adv_firm_roster` is
      added.
- [ ] All pre-existing tests in the touched files still pass.
