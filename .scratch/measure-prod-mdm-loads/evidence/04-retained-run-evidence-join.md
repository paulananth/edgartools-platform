# Evidence — retained run verification and the evidence join

Date checked: 2026-11-13. Read-only inspection of local retained evidence. No production database
connection was made; every run record comes from the retained export.

## The three evidence sources, and which one is authoritative for what

| Source | Path | What it holds | Freshness |
|---|---|---|---|
| A. Bookkeeping run export | `~/.local/share/edgartools/load-logs/measure-prod-runs-verified.json` (391 rows), `measure-prod-runs.json` (391 rows) | Per-run: `run_id`, `source`, `target`, `state`, `units`, `verified`, `pending`, `created`, `completed`, `capture`, `rule_version`, `worklist_hash`, `rules_sha`, `inputs_sha`, `inputs_uri` | Runs created 2026-11-11 02:57 UTC → 2026-11-12 16:55 UTC |
| B. Load-log summaries | `~/.local/share/edgartools/load-logs/measure-prod-load-summaries.json` (32 invocations), plus the raw `.log` files in the same directory | Per invocation: log file name, `considered`, `new`, `already`, `bundles`, `run_ids` | Same window |
| C. Private manifest tree | `~/.local/share/edgartools/hosted-prod/manifests/load/<source>/<target>/` | Per run directory: `bundle-NNN/documents.json`, `bundle-NNN/manifest/*.json` (staged, merge, processed), and a `reports/` directory of per-step receipts | Run directories dated **2026-11-12 22:32 UTC → 2026-11-13 15:07 UTC** |

**A and B cover the original loads (Nov 11–12). C covers a later, separate set of runs (Nov 12–13).**

## 1. The join key — and why A and C do not join to each other

- **A → B** joins on `run_id`. It is a clean join: of the 32 invocations, 16 carry at least one run
  id present in A (e.g. `hosted-person-loop-body.log` carries 149 run ids, 123 of them in A;
  `hosted-hosted-openfigi-nport-v2.log` carries 16, all 16 in A). The other 16 invocations are
  `golive-*` and `small-golive-*` logs whose run ids are **not** in A — they predate the export or
  belong to runs the export does not carry.
- **A → C** does **not** join. The overlap between A's 391 run ids and the 502 run ids inside C's
  `reports/` files is **zero**. A's `inputs_uri` values point at manifest paths that no longer
  exist: all 391 point under `manifests/load/`, and **391 of 391 are missing from disk**.
- The reason is visible in the timestamps: A's runs were created 2026-11-11 02:57 → 2026-11-12
  16:55 UTC; C's earliest run directory is `2026-11-12T223255Z` and the latest is
  `2026-11-13T150704Z`. The manifest tree was rebuilt after the export was taken, and the
  pre-existing manifest directories were removed.

**Consequence:** C is not a second copy of A's evidence. It is evidence of a *later* wave of runs
against the same production store, on the same targets, with the same capture families. It cannot
be used to complete A's rows, and A cannot be used to verify C's runs.

## 2. A: which runs meet the acceptance bar

Export totals: 391 runs across 15 source/target pairs; **358 `complete`, 33 `running`**; 0 failed.

Acceptance bar = `state == complete` **and** `verified == units` **and** `pending == 0`.

| Source/target | Runs | Complete | Verified runs | Bar met? | First run created (ET) | Last verified completion (ET) |
|---|---|---|---|---|---|---|
| `sec.company/mastering` | 172 | 172 | 172 | yes | 2026-11-11 13:32:16 | 2026-11-11 16:39:37 |
| `sec.submissions.person/mastering` | 149 | 149 | 149 | yes | 2026-11-11 23:18:17 | 2026-11-12 02:31:53 |
| `openfigi/mastering` | 35 | 18 | 18 | **partial** | 2026-11-11 00:33:29 | 2026-11-11 23:25:49 |
| `sec.ownership/mastering` | 9 | 8 | 8 | **partial** | 2026-11-11 23:09:14 | 2026-11-12 05:53:25 |
| `sec.nport.security/mastering` | 6 | 0 | 0 | **partial** | 2026-11-10 22:27:15 | — |
| `gleif/mastering` | 7 | 0 | 0 | **partial** | 2026-11-11 23:19:34 | — |
| `iapd.adv/custodians` | 3 | 2 | 2 | **partial** | 2026-11-11 16:47:35 | 2026-11-11 17:12:10 |
| `iapd.adv/mastering` | 2 | 2 | 2 | yes | 2026-11-11 16:54:59 | 2026-11-11 17:15:56 |
| `sec.registration/silver` | 2 | 2 | 2 | yes | 2026-11-11 23:07:53 | 2026-11-12 01:56:54 |
| `sec.nport.registrant/mastering` | 1 | 1 | 1 | yes | 2026-11-10 22:00:23 | 2026-11-10 22:04:11 |
| `sec.nport.fund/mastering` | 1 | 1 | 1 | yes | 2026-11-11 00:21:33 | 2026-11-11 00:33:20 |
| `sec.thirteenf.securities/mastering` | 1 | 1 | 1 | yes | 2026-11-10 22:04:23 | 2026-11-10 22:26:58 |
| `sec.thirteenf.filings/silver` | 1 | 1 | 1 | yes | 2026-11-11 23:06:22 | 2026-11-11 23:07:26 |
| `gleif/subfund-pairs` | 1 | 1 | 1 | yes | 2026-11-10 21:57:34 | 2026-11-10 22:00:11 |
| `sec.company-facts/silver` | 1 | 0 | 0 | **partial** | 2026-11-11 23:16:44 | — |
| `sec.ownership/security_symbols` | 0 | — | — | **blocked** | — | — |

Times converted from the export's UTC `created`/`completed` to ET. Every `complete` run also has
`verified == units` and `pending == 0`; the 33 `running` runs are the shortfall in every partial
row.

`sec.nport.security/mastering_other_keys` has **no rows at all** in A: it does not appear in the
export. Its only evidence is in C (4 run directories, 4 bundles, 4 report files, steps `record`,
`prepare`, `merge`).

## 3. B: the load-log summaries

`measure-prod-load-summaries.json` holds 32 invocations across 12 source/target pairs. All 32
reconcile: `considered == new + already` (verified by recount). The log files exist under the same
directory, and each carries a `Done:` summary line (e.g. `hosted-13f-filings-v1.log`:
`Done: 10 documents loaded, 0 already loaded before`).

**No log contains `time -p` output** — a scan for `real `/`user `/`sys ` lines across every `*.log`
in the directory returns nothing, and no `elapsed` marker exists either. Therefore
`active_command_seconds` is unavailable for every target, and `target_wall_seconds` cannot be
derived from a log: the logs carry no invocation start or end timestamp, only the `Done:` summary
and the run ids.

The summaries are what give the report its **per-invocation** record: `considered`, `new` (selected),
`already`, `bundles`, `run_ids`, and the log file name. They do not carry timestamps.

## 4. C: the later manifest wave

Per target, the private manifest tree holds run directories (UTC-stamped), bundles, documents and
per-step receipts:

| Source/target | Run dirs | Bundles | Documents | Report files | Report run ids |
|---|---|---|---|---|---|
| `sec.company/mastering` | 4 | 360 | 183,480 | 900 | 300 |
| `sec.submissions.person/mastering` | 1 | 149 | 76,231 | 712 | 149 |
| `openfigi/mastering` | 3 | 27 | 12,838 | 51 | 17 |
| `sec.ownership/mastering` | 2 | 22 | 10,712 | 159 | 11 |
| `sec.registration/silver` | 1 | 2 | 732 | 230 | 2 |
| `sec.company-facts/silver` | 3 | 3 | 1,104 | 720 | 3 |
| `iapd.adv/mastering` | 4 | 4 | 4 | 40 | 4 |
| `iapd.adv/custodians` | 4 | 4 | 4 | 24 | 4 |
| `sec.nport.security/mastering` | 1 | 1 | 1 | 17 | 1 |
| `sec.nport.security/mastering_other_keys` | 4 | 4 | 4 | — | 0 (no `reports/` dir) |
| `sec.nport.registrant/mastering` | 2 | 2 | 2 | 16 | 2 |
| `sec.nport.fund/mastering` | 1 | 1 | 1 | 11 | 1 |
| `sec.thirteenf.securities/mastering` | 1 | 1 | 52 | 44 | 1 |
| `sec.thirteenf.filings/silver` | 1 | 1 | 10 | 3 | 1 |
| `gleif/mastering` | 2 (+1 `preparation`) | 2 | 2 | 7 | 5 |
| `gleif/subfund-pairs` | 1 | 1 | 1 | 2 | 1 |

Each `reports/<sha>.json` is a step receipt with `binding.run_id`, `binding.step`, `binding.key`,
`binding.attempt`, `binding.effect_key`, a candidate manifest URI + sha256, a `checks` map, and a
`runtime` digest. The steps present per target match the Rules expansion in the inventory evidence
(e.g. `sec.company/mastering` reports `records`, `merge`, `processed`; `sec.ownership/mastering`
reports `read`, `merge`, five `land_*` steps and `processed`).

**C has no verification state.** The report files record that a step was performed and which checks
passed; they carry no `verified`/`pending` counts and no per-unit accounting. A `checks` map with
`mdm.committed: true` is not the acceptance bar's `expected == verified, pending == 0`.

## 5. The join, stated as a rule

1. **Bookkeeping run export (A) is the only source of run state.** `state`, `units`, `verified`,
   `pending`, `created`, `completed` come from A and nowhere else.
2. **Load-log summaries (B) attach to A's runs by `run_id`.** Where a summary's run ids are all
   present in A, the invocation's `considered`/`new`/`already`/`bundles` counts and its log file
   name join to those runs. Where they are not (the 16 `golive-*`/`small-golive-*` invocations), the
   invocation is **historical-only**: the log is evidence that the load happened, but the current
   export cannot verify its runs.
3. **The private manifest tree (C) does not join to A.** Zero run-id overlap; A's manifest paths
   are gone. C is a **separate, later wave** on the same targets. It is evidence that the target was
   loaded again after the export, and it supplies per-step receipts and document counts — nothing
   that verifies A's runs, and nothing that A verifies.
4. **Precedence when sources disagree:** A's run state wins over B's log narrative for state, units
   and pending; B's counts win over nothing (A carries no `considered`/`new`/`already`); C never
   overrides A. A disagreement is recorded as a note on the row, not silently resolved.
5. **A target's verification verdict is A's verdict for the measured window** — the window A
   covers, 2026-11-11 02:57 UTC → 2026-11-12 16:55 UTC. C's later wave is reported separately
   (its own run ids, bundle counts and receipt counts) and does not upgrade a `partial` row to
   `complete`, because C carries no verification state.

## 6. What the acceptance bar yields

- **8 targets** meet the bar in A: `sec.company/mastering`, `sec.submissions.person/mastering`,
  `iapd.adv/mastering`, `sec.nport.registrant/mastering`, `sec.nport.fund/mastering`,
  `sec.thirteenf.securities/mastering`, `sec.thirteenf.filings/silver`, `sec.registration/silver`,
  `gleif/subfund-pairs` — nine in total, counting `gleif/subfund-pairs`.
- **5 targets are partial** in A: `gleif/mastering` (0 of 7 verified), `openfigi/mastering` (18 of
  35), `sec.ownership/mastering` (8 of 9), `iapd.adv/custodians` (2 of 3),
  `sec.nport.security/mastering` (0 of 6), `sec.company-facts/silver` (0 of 1) — six in total.
- **1 target is blocked**: `sec.ownership/security_symbols` — zero runs in A.
- **1 target has no A evidence at all**: `sec.nport.security/mastering_other_keys` — evidenced only
  by C (4 bundles, 4 step receipts), with no verification state.

## 7. Timing fields that follow from the join

| Field | Available? | Why |
|---|---|---|
| `first_run_created_at_et`, `last_verified_run_completed_at_et` | yes, per A | run records carry both timestamps |
| `retained_run_span_seconds` | yes, per A | last completion − first creation; a **run span**, not an invocation wall time |
| `target_wall_seconds` | **no** | no invocation start/end timestamp survives in any retained source |
| `active_command_seconds` | **no** | no `time -p` output survives in any log |
| `mdm_write_step_seconds` | yes, for targets with `prepare`/`merge` steps | from `measure-prod-step-intervals.json` (1,442 intervals retained) |
| considered / selected / already / bundles / run ids | yes, per B, for 32 invocations | the load-log summaries |

This matches the 2026-11-12 snapshot exactly (`target_wall_seconds: null` with
`target_wall_unavailable_reason: "Exact first invocation start absent; retained run span is not
invocation wall time."`, `active_command_seconds: null` with `"No retained time -p real output."`).
The new fact is the **manifest-tree rebuild**: there is a later wave of runs against the same
production store that the export does not cover, and whose verification state is not retained.
