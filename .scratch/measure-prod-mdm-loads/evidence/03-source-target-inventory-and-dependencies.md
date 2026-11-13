# Evidence — source/target inventory and dependencies in this checkout

Date checked: 2026-11-13, against branch `codex/wayfinder-measure-prod-loads-20261113` (from
`origin/main`, HEAD `5b80f795f`).

The inventory was produced by expanding every source document through
`edgar_warehouse.rules.files.source(name, root, steps=True)`, which runs the same
`edgar_warehouse/rules/shape.py` expansion the engine uses. It is not read off the YAML by hand.

## 1. Configured source/target names — **19**, not 16

The checkout configures **19** source/target names across 13 sources:

| # | Source/target | Kind | Steps (exact names) |
|---|---|---|---|
| 1 | `sec.company/mastering` | mastering (`local: true`) | `main`, `catalog`, `combine`, `records`, `merge`, `processed` |
| 2 | `sec.company/capture` | capture | `capture` |
| 3 | `gleif/mastering` | mastering | `read`, `prepare`, `merge`, `links`, `processed` |
| 4 | `gleif/subfund-pairs` | mastering | `pairs`, `processed` |
| 5 | `sec.submissions.person/mastering` | mastering | `read`, `records`, `merge`, `processed` |
| 6 | `iapd.adv/mastering` | mastering | `read_filings`, `read_custody`, `read_ciks`, `read_related`, `combine`, `record`, `prepare`, `merge`, `land_custody`, `processed` |
| 7 | `iapd.adv/custodians` | mastering | `read_custody`, `combine`, `record`, `prepare`, `merge`, `processed` |
| 8 | `sec.ownership/mastering` | mastering | `read`, `prepare`, `merge`, `land_owner`, `land_nd_transaction`, `land_nd_holding`, `land_d_transaction`, `land_d_holding`, `processed` |
| 9 | `sec.ownership/security_symbols` | mastering | `read_security`, `prepare_security`, `merge_security`, `processed_security` |
| 10 | `sec.thirteenf.securities/mastering` | mastering | `read`, `reduce`, `combine`, `record`, `prepare`, `merge`, `land_holding`, `processed` |
| 11 | `sec.nport.registrant/mastering` | mastering | `submissions`, `registrants`, `ciks`, `combine`, `record`, `prepare`, `merge`, `processed` |
| 12 | `sec.nport.fund/mastering` | mastering | `submissions`, `registrants`, `filings`, `series`, `pairs`, `combine`, `record`, `prepare`, `merge`, `links`, `processed` |
| 13 | `sec.nport.security/mastering` | mastering | `identifiers`, `holdings`, `reduce`, `filings`, `issuers`, `issuer_reduce`, `combine`, `record`, `submissions`, `registrants`, `series`, `holding`, `prepare`, `merge`, `land_holding`, `links`, `processed` |
| 14 | `sec.nport.security/mastering_other_keys` | mastering | `record`, `prepare`, `merge` |
| 15 | `openfigi/mastering` | mastering (`local: true`) | `requests`, `answers`, `reduce`, `line_counts`, `lines`, `listing`, `combine`, `record`, `prepare`, `merge`, `processed` |
| 16 | `sec.company-facts/silver` | silver | `facts`, `land`, `line_items`, `measures`, `processed` |
| 17 | `sec.thirteenf.filings/silver` | silver | `filings`, `land`, `processed` |
| 18 | `sec.registration/silver` | silver | `read`, `land_offering`, `land_statement_line`, `processed` |
| 19 | `sec.registration/capture` | capture | `capture` |

The 2026-11-12 snapshot counted **16** because it excluded the three capture targets
(`sec.company/capture`, `sec.registration/capture`) and `sec.nport.security/mastering_other_keys`.
The plan's own rule — "capture targets are not run" and "do not run the separate
`sec.company/merge-batch` target" — excludes the two capture targets from the measurement, which
leaves **17** measured names, one more than the plan's 16.

**`sec.nport.security/mastering_other_keys` is the difference.** It is a real configured target
(`rules/sources/sec.nport.security/source.yaml`), it has a private manifest tree
(`hosted-prod/manifests/load/sec.nport.security/mastering_other_keys/`, 4 run directories, 4
bundles), and it was executed. It is not a capture target, so the plan's exclusion does not cover
it. It is not in `rules/source-sequence.yaml` either. The report's inventory decision therefore
has 17 measured names, and `mastering_other_keys` must be given a row — or explicitly excluded
by a rule the operator confirms. That choice belongs to the report-shape ticket.

`sec.company/merge-batch` does **not** exist in this checkout.

## 2. Sequence sources — 13, matching the plan

`rules/source-sequence.yaml` declares exactly 13 sources, each with a `target`:

`sec.company` (mastering), `gleif` (mastering), `sec.submissions.person` (mastering),
`iapd.adv` (mastering), `sec.ownership` (mastering), `sec.thirteenf.securities` (mastering),
`sec.nport.registrant` (mastering), `sec.nport.fund` (mastering), `openfigi` (mastering),
`sec.nport.security` (mastering), `sec.company-facts` (silver), `sec.thirteenf.filings` (silver),
`sec.registration` (silver).

All 13 declare `requires: []`. The file's own header states the rule: "`after` is a preferred
order only; it never pulls another source into a run. Declare `requires` only for genuine
required source inputs, not waiting links."

**There is no hard source-to-source dependency anywhere in the sequence.** Ordering is a
preference, and the three link targets are ordered by the Rules themselves.

## 3. The three ordered targets — and where their ordering actually comes from

| Target | Ordering claim in the plan | What the Rules say | Hard dependency? |
|---|---|---|---|
| `gleif/subfund-pairs` → `sec.nport.security` | runs before its consumer | `sec.nport.security`'s `source.yaml` pass `submissions` reads `sec.nport.fund/submissions.yaml`; `gleif/subfund-pairs.yaml` is a GLEIF rules file. `shape.py`'s `_waits()` derives the wait from the `readings`/`lookups` `from:` field | **Derived from the pass graph inside the target**, not from `source-sequence.yaml`. `after:` in the sequence lists `sec.nport.security` after `sec.thirteenf.securities` only. |
| `iapd.adv/custodians` → `iapd.adv/mastering` | runs before its consumer | `iapd.adv/mastering`'s `source.yaml` silver step `land_custody` declares `requires: ["read_custody", "merge"]` — an explicit intra-target `requires`, satisfied by `mastering`'s own `read_custody` pass, not by the separate `custodians` target | **No cross-target `requires`.** The `custodians` target masters `iapd.adv.custodians.v1` into the `custody` table; `mastering` reads custody records through its own `read_custody` pass and lands `adv_custody`. The two targets share a dataset family but the ordering is not enforced by the Rules. |
| `sec.ownership/security_symbols` → after OpenFIGI | runs after OpenFIGI security data is present | `sec.ownership/security_symbols` masters `sec.ownership.security.v2` into `security_record`; the security kind's sources are `openfigi.security.v4`, `sec.thirteenf.securities.v2`, `sec.nport.security.v2`, `sec.ownership.security.v2` | **No declared dependency.** The order is a semantic one (Form 4 securities resolve against identifiers OpenFIGI creates), and it is the reason the target was `blocked` in the 2026-11-12 snapshot. |

So all three are **sequencing preferences stated in prose**, with one partial Rules support
(`gleif/subfund-pairs` is read inside a pass of the consumer). The report must therefore present
them as the measurement order to follow, not as enforced dependencies — and must say which
ordering it used and on what basis.

## 4. Declared dataset codes per target

From `rules/sources/<source>/source.yaml` (`dataset_contracts` and each target's `master.keys`):

| Source | Dataset contracts | Mastered dataset → table |
|---|---|---|
| `sec.company` | `sec.company.v1` | `sec.company.v1` → `company` |
| `gleif` | `gleif.level1.v1`, `gleif.relationships.v1`, `gleif.reporting_exceptions.v1` | `gleif.level1.v1` → `level1` |
| `sec.submissions.person` | `sec.submissions.person.v1` | `sec.submissions.person.v1` → `submissions` |
| `iapd.adv` | `iapd.adv.filings.v2`, `iapd.adv.custodians.v1` | `iapd.adv.filings.v2` → `filings`; `iapd.adv.custodians.v1` → `custody` |
| `sec.ownership` | `sec.ownership.security.v2`, `sec.ownership.reporting_owner.v1` | `sec.ownership.reporting_owner.v1` → `owner_record`; `sec.ownership.security.v2` → `security_record` |
| `sec.thirteenf.securities` | `sec.thirteenf.securities.v2` | `sec.thirteenf.securities.v2` → `security` |
| `sec.nport.registrant` | `sec.nport.registrant.v2` | `sec.nport.registrant.v2` → `registrant` |
| `sec.nport.fund` | `sec.nport.fund.v1` | `sec.nport.fund.v1` → `fund` |
| `sec.nport.security` | `sec.nport.security.v2` | `sec.nport.security.v2` → `security` (both `mastering` and `mastering_other_keys`) |
| `openfigi` | `openfigi.security.v4` | `openfigi.security.v4` → `security` |
| `sec.company-facts` | — (silver only) | — |
| `sec.thirteenf.filings` | — (silver only) | — |
| `sec.registration` | — (silver only) | — |

## 5. Entity kinds — the map comes from `rules entity-types`, cross-checked against the merge kinds

The plan names one authority: "Build the source/dataset-to-kind map from active Dataset Contracts
returned by `rules entity-types`". That command was run in this checkout (the implementation is
`edgar_warehouse/rules/cli.py:30`, calling `files.entity_types`, which reads each contract's
`adapter.kind`, `adapter.classification.kind`, or `adapter.kind_field` + `kind_values`).

`rules entity-types` returns **14 contracts**:

| Kind | Contracts (with how the kind is decided) |
|---|---|
| `company` (7) | `gleif.level1.v1` (source field), `gleif.relationships.v1` (fixed), `gleif.reporting_exceptions.v1` (fixed), `iapd.adv.custodians.v1` (fixed), `iapd.adv.filings.v2` (fixed), `sec.company.v1` (rule `sec-company-candidate`), `sec.nport.registrant.v2` (fixed) |
| `security` (4) | `openfigi.security.v4`, `sec.nport.security.v2`, `sec.ownership.security.v2`, `sec.thirteenf.securities.v2` (all fixed) |
| `person` (2) | `sec.ownership.reporting_owner.v1` (rule `sec-ownership-person`), `sec.submissions.person.v1` (rule `sec-person-candidate`) |
| `fund_structure` (1) | `sec.nport.fund.v1` (fixed) |

`rules/merge/kinds/*.yaml` gives each kind its `defaults.sources` and its per-rule `source`:

| Kind | Kind file version | Contributing dataset codes (from `defaults.sources` + rule sources) |
|---|---|---|
| `company` | `company-2026-10-31.sec-company-source-identity` | `sec.company.v1`, `gleif.level1.v1`, `gleif.relationships.v1`, `iapd.adv.filings.v2`, `iapd.adv.custodians.v1`, `sec.nport.registrant.v2` |
| `person` | `person-2026-10-25.one-value-per-identifier` | `sec.submissions.person.v1`, `sec.ownership.reporting_owner.v1` |
| `security` | `security-2026-11-02.thirteenf-source-is-securities` | `openfigi.security.v4`, `sec.thirteenf.securities.v2`, `sec.nport.security.v2`, `sec.ownership.security.v2` |
| `fund_structure` | `fund_structure-2026-10-25.one-value-per-identifier` | `sec.nport.fund.v1` |

### The two authorities differ by exactly one contract

| Kind | `rules entity-types` | merge-kind `defaults.sources` | Difference |
|---|---|---|---|
| `company` | 7 | 6 | `gleif.reporting_exceptions.v1` is in entity-types but **not** in the merge kind's source list |
| `person` | 2 | 2 | — |
| `security` | 4 | 4 | — |
| `fund_structure` | 1 | 1 | — |

Every merge-kind rule source appears in the corresponding `defaults.sources` list, and every
`defaults.sources` member has a rule. The single disagreement is
`gleif.reporting_exceptions.v1`: the Dataset Contract states its records' entity type is
`company`, but the company merge kind does not list it — it maps no field and no rule.

**This is the one ambiguity the entity-model ticket must settle.** The two readings differ:

- `rules entity-types` (the plan's named authority) → 14 contracts; the reporting-exceptions
  contract is a company contributor, and its target `gleif/mastering` counts toward company
  completeness.
- merge-kind `defaults.sources` (what actually writes and binds) → 13 contracts; the
  reporting-exceptions contract contributes no field and no rule, so it does not gate company
  completeness.

Three sources have **no** kind at all: `sec.company-facts`, `sec.thirteenf.filings`,
`sec.registration` (silver targets only). `gleif/subfund-pairs`, `iapd.adv/custodians`,
`sec.ownership/security_symbols` and `sec.nport.security/mastering_other_keys` are *targets*, not
sources — they carry no kind of their own; their datasets appear under their source's kind.

## 6. `scripts/run_inputs.py`

`scripts/run_inputs.py` exists at the checkout root and is the declared-inputs resolver the plan
names. It is the tool that yields each target's `--fact name=value` and `--file name=path`
arguments from the active Rules and the retained manifest — not a source of the inventory itself.

## 7. What this changes for the plan

1. The inventory is **17 measured names**, not 16, unless `sec.nport.security/mastering_other_keys`
   is excluded by an explicit rule.
2. All 13 sequence sources declare `requires: []`; **no source ordering in the sequence is a hard
   dependency**. The three link orderings are prose preferences with partial Rules support, and
   the report must state the basis it used for ordering.
3. The entity-kind map has **14 contracts** under `rules entity-types` (the plan's named authority:
   7 company, 4 security, 2 person, 1 fund_structure) and **13** under the merge kinds'
   `defaults.sources` (6 company, 4 security, 2 person, 1 fund_structure). The single difference is
   `gleif.reporting_exceptions.v1`, which states `company` in its Dataset Contract but maps no
   field and no rule in the company kind. The entity-model ticket settles which reading the report
   uses; either way the report must state the count it used and why.
