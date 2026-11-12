# The two targets: MDM and silver

Part of the `data-onboarding` skill: [SKILL.md](SKILL.md) says when to read this.

## Two targets: MDM and silver

Every step says what differs for each target.

- **MDM target.** The feed's records become MDM records through its
  Dataset Contract (`dataset_contracts` section) and its kind's merge rules. Everything in
  this skill builds it.
- **Silver target.** A transaction or published reference part lands in a
  silver table made from its approved silver table spec (the part's `silver`
  in `findings.yaml`). The spec's links point to master parts only; fill each
  link's `kind` and `source_code` (the master's Dataset Contract) from the
  onboarded master, since the writer looks each row's MDM id up by them and
  refuses a link without them.
  - **One link, one Dataset Contract.** The writer finds a row's MDM id by
    the source key among the records that one Dataset Contract staged. When
    a key may have been staged by either of two contracts (one column holding
    either of two identifier types), give that column two links, each with its
    own MDM id column; each row fills the one whose contract staged its key.
  - **A master whose record key has several parts** is found by that key as
    MDM writes it: the parts as a compact JSON list (`["<part 1>","<part 2>"]`).
    Build that text as a column in the reading (`concat` of the parts) and
    test it against `adapters.record_key` on the master's contract.
  - **Keep the source's own shape for rows several parties share.** When one
    record names several parties for the same lines, land the lines once and
    the parties in their own table, joined by the record's key, as the source's
    own published data sets do; never repeat a line per party, or a sum over
    parties counts it several times.
  - **The spec goes in the repo.** Write the approved spec to
    `rules/sources/<source>/silver-<table>.yaml` (comments carry the rulings),
    put the same spec in the part's `silver` in `findings.yaml`, and
    regenerate `profile.yaml` (**plan-parts**), so the catalog shows the table
    that is registered.
  - **Its checks are in the spec.** The data-quality skill writes them into
    the spec's `checks`; a failing row lands flagged in its `quality` column.
  - **Prove the link.** A test lands invented rows beside the master's
    records, keyed apart from the identifier, and asserts each MDM id; a link
    pointed at another Dataset Contract must fail it.

  - **A link stated on each transaction row is a lookup, not an MDM record**
    (a fund's holding of a security, an order's supplier). Land the rows in
    silver with one link per master; the writer fills each MDM id by its key.
    Never stage one MDM record per row only to master the link (operator: "Why do you need to merge it it's just a lookup").
  - **Never carry a many-to-many link as a list on a record.** A reduction keeps
    at most 1,000 members per list (`sample_limit`), so a widely held entity
    loses links silently: one row per link instead.
  - **The row's link key is the master's record key, as its contract makes
    it.** Repeat the contract's own choice (an identifier, else another, a
    folded key) in the rows' contract, and prove every row's key is a record
    key the master's contract makes from the same files.
  - **Rows for silver get their own reading**, beside the master's, so the
    master's reading and its pinned digests do not change.
  - **Limits on a production feed are the engine's ceilings** (operator: "No limit on production", "I asked to remove all limits").
    The engine requires each to be declared, so "no limit" means its ceiling:
    a stream's `max_input_bytes`, `max_bytes` and `max_spool_bytes` 1 TiB,
    `max_records` and `max_output_rows` 10^12, `max_partitions` 10^7,
    `max_record` 32 MiB, `partition_bytes` 8 MiB, `partition_records`
    100,000; a lookup set's `max_values` 100,000,000, `max_bytes` 16 GiB,
    `max_value_bytes` 16,384; a combine's `max_rows` 40,000,000; a reading
    over pieces `execution.max_input_bytes` and `limits.max_bytes` 16 GiB,
    `limits.max_records` 100,000,000. A streamed reading's `read.limits`
    bounds one row: at most 32 MiB and 100,000.
  - **Check it on the largest real case before any run** (operator: "make sure the logic is correct and works for a major fund
    issuer"): cut that case's files out of the capture, run the real
    contracts on them in pieces as a run cuts them (8 MiB, 100,000 rows; a
    large combined output arrives as a version-2 index of pieces), and count
    every row by outcome.
  1. Hand the approved spec to
  [data-operations](../data-operations/SKILL.md), which applies it as DDL.
  Use the owner and runtime connections from [Connection URLs and environment](../data-platform/SKILL.md#connection-urls-and-environment).
  On PostgreSQL the schema owner runs
  `edgar-warehouse silver init --runtime-role <runtime login>` once, and
  `edgar-warehouse silver register rules/sources/<source>/silver-<table>.yaml --runtime-role <runtime login>`
  for the table (or `register <findings.yaml> --part <part>`). A changed
  spec is refused for a registered table: register it as a new table.
  `edgar-warehouse load` does this itself before it submits anything: for each
  `silver.land` step it registers the `silver-*.yaml` beside the source's rules
  whose `table` the step names, as the stores' migration login,
  for the silver runtime login. It changes nothing for a table already registered
  with the same spec, so a source with a spec beside its rules needs no
  preparation by hand.
  MySQL and SQL Server Express use the same spec. When `silver register`
  refuses that dialect, data-operations reports the gap and does not
  hand-write `CREATE TABLE`.
  2. A target lands a table through a `silver.land` step (`requires` the reading
     and the merge whose masters the rows link to; `input: {keys: {table, silver}}`;
     the Change Journal's `journal.record` requires it), as a source's transaction rows do.
     Otherwise the runtime, with MDM read access configured through the central
     connection section, runs `edgar-warehouse silver land <table> <rows file>` with the
     part's rows as a flat CSV, Parquet or JSON Lines file. A rerun of the same
     delivery changes nothing; an unmastered record keeps its source key and an
     empty MDM id. Once its master is onboarded, `edgar-warehouse silver
     refresh-ids <table>` fills the ids of rows already landed.
  3. `edgar-warehouse context silver <table>` shows an agent what the table holds.

  Scheduled landing through the declared pipeline still needs a verified
  output worker (`edgar-warehouse workers describe <profile>`); Bookkeeping
  owns orchestration. A missing profile is unfinished implementation: record
  the gap.
