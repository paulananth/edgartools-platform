# What would a v2 Mongo document be?

Ticket: `.scratch/mongodb-v2-agent-interface/issues/02-inventory-bundle-json-as-mongo-documents.md`

Scope: in-repo Python bundle/feature-screen/watermark dicts, serving writers,
ADR 0001 / CONTEXT.md, and official MongoDB BSON size. No Atlas provision.
No Mongo writer. Does not reopen
[contract research 10](../../agent-decision-contract/research/10-json-mongodb-agentic-data-plane.md)
v1 verdict (Mongo is not v1 Agent SoE). This map is additive v2.

## Question

What would a v2 Mongo document be, given the in-repo bundle is already a
nested Python dict and there is no Mongo in the repo?

## Verdict

A v2 Mongo document **would be** a BSON projection of the same nested
Decision Graph Bundle Python `dict` that
`build_issuer_subject_bundle` already returns (CIK-rooted envelope +
`sections` + coverage + `agent_grade` + four-field watermark identity),
optionally split so Feature Screen rows and neighborhood edges are their
own documents. It would **not** be a second warehouse, not bronze/silver
ingest, and not a replacement for the v1 Snowflake Decision Contract.

There is no persisted JSON agent SoE today. `json.dumps(bundle)` is free
serialization of an in-memory spec; nothing in-repo writes that dict to a
document store.

---

## Field inventory

### `build_issuer_subject_bundle` — one nested payload

Source: `edgar_warehouse/serving/subject_bundle_read.py` (locked by
`tests/unit/test_subject_bundle_read.py`). Callers inject gold/graph rows;
the function does not query Snowflake or Mongo.

**Top-level keys** (always present):

| Key | Type in Python | Notes |
| --- | --- | --- |
| `bundle_subject_cik` | `int` | Bundle Subject; CIK as integer, not zero-padded string |
| `bundle_kind` | `"issuer"` | Pure-issuer path; manager ADV is out of this map |
| `decision_contract_version` | `str` | From `evaluate_agent_grade`; falls back to `DECISION_CONTRACT_VERSION` (`"1"`) |
| `decision_watermark_identity` | `dict` or `None` | Four-field pin, **not** full `DecisionWatermark.to_dict()` |
| `agent_grade` | `bool` | Fail-closed result of `evaluate_agent_grade` |
| `agent_grade_reasons` | `list[str]` | Empty when grade is true |
| `include_neighborhood_history` | `bool` | Flag only; history rows are not populated in this builder |
| `sections` | `dict` | Eight named sections, or `{}` when subject is out of universe |

Out-of-universe short-circuit (`subject_in_decision_universe=False`): same
envelope, `agent_grade=False`, extra reason `"subject not in Decision Subject
Universe"`, `sections={}`.

**`decision_watermark_identity` subset** (same helper in bundle and screen):

```text
business_date, gold_run_id, graph_generation_id, decision_contract_version
```

Omitted from the identity pin (present on full `DecisionWatermark.to_dict()`):
`silver_completeness_ok`, `graph_parity_ok`, `bronze_content_hashes`,
`bronze_persist_used`, `high_severity_reconcile_open`, `reconcile_waived`,
`notes`. CONTEXT **Decision Watermark** still treats a bronze digest as
mandatory for an Agent-Grade Read. A Mongo document that copied only the
Python identity pin would **not** carry bronze hashes unless a writer added
the full watermark.

**`sections` keys** (stable constants in `subject_bundle_read.py`):

| Section | Coverage | Nested shape |
| --- | --- | --- |
| `insiders` | present / empty / unavailable | `rows[]` of agent-grade edges; `non_agent_grade.unresolved_graph_edges[]` + `gold_only_unresolved[]` |
| `employment` | present / empty / unavailable | `rows[]` (`EMPLOYED_BY`); `executive_pay[]` from gold proxy |
| `holders_of_subject` | present / empty / unavailable | `section`, `holdings_period` lag meta, `rows[]` via `dict(r)` passthrough |
| `subject_as_manager_portfolio` | present / empty / unavailable | Same holdings shape; empty period meta allowed |
| `auditor` | present / unavailable | `rows[]` sorted PCAOB-id first; `identity_rule=prefer_auditor_evidence_pcaob_id` |
| `has_parent` | present / empty / unavailable | `scope=registrant_disclosed`, `inventory_complete`; incomplete inventory → unavailable + empty `rows` |
| `subject_features` | FY coverage + interim coverage | 19-key `fy_features` / `interim_features` vectors + period_end + coverage |
| `adv` | always `not_applicable` | `reason=pure_issuer_bundle_does_not_require_adv`, `rows=[]` |

**Insider agent-grade row:** `person_entity_id`, `person_name`,
`relationship_type` (`IS_INSIDER` default), `source_accessions[]`,
`agent_grade_edge=True`. Graph-without-gold and gold-only names are never
in `rows`; they live under `non_agent_grade`.

**Employment row:** `person_entity_id`, `person_name`, `role_title`,
`source_system` (`proxy_def14a` / `item_5_02` constants; unknown still
surfaces), `relationship_type=EMPLOYED_BY`, `effective_date`. Pay:
`person_name`, `exec_role`, `compensation_amount`, `accession_number`,
`source=gold_proxy_executive_record`.

**Holdings period meta:** `latest_complete_holdings_period`, `period_end`,
`lag_days`, `as_of_business_date`. Holder **row keys are not a closed
schema** — `_build_holdings_section` does `[dict(r) for r in rows]`.

**Subject features section:** `coverage` (FY), `fy_features` (19 keys),
`fy_features_coverage`, `fy_period_end`, `interim_features` (19 keys),
`interim_features_coverage`, `interim_period_end`. Interim missing →
`not_applicable`. All-null FY vector → `empty`, not `unavailable`.

v1 agent-grade **content** (CONTEXT Trading-Relevant Neighborhood) is
As-Of features + current `IS_INSIDER` + current `EMPLOYED_BY`. Holders,
auditor, parent remain on the payload as keys; v1 treats them unavailable
until bind exists. ADV stays `not_applicable` on issuer bundles.

Compact JSON size of one **empty-section** issuer bundle from the live
function: **1,964 bytes**. A modest neighborhood (20 insiders, 10
employment, 1 holder, auditor, FY vector): **6,745 bytes**. Nested depth
is ~4 (envelope → sections → rows → field), well under MongoDB’s 100-level
BSON nesting cap.

### `build_subject_feature_screen` — one payload wrapping a universe of rows

Source: `edgar_warehouse/serving/subject_feature_screen.py` (locked by
`tests/unit/test_subject_feature_screen.py`).

**Top-level (one Python return value, one screen):**

| Key | Meaning |
| --- | --- |
| `decision_contract_version` | `"1"` |
| `agent_grade` | bool from `evaluate_agent_grade` |
| `agent_grade_reasons` | list |
| `decision_watermark_identity` | same four-field pin |
| `universe_size` | `len(warehouse_active ∩ mdm_active)` |
| `rows` | **one dict per universe CIK**, including members with no factor periods |

Fail-closed watermark still returns `rows` (audit/debug); `agent_grade` is
false. Market-price fields are stripped (`FORBIDDEN_MARKET_FIELDS`).

**Per-CIK row** (this is the ranking grain, not the whole screen):

```text
cik
fy_features                  # 19-key PURE_SEC_FEATURE_KEYS vector
fy_features_coverage         # present | empty | unavailable
fy_period_end, fy_fiscal_year, fy_accession_number
interim_features             # 19-key vector
interim_features_coverage    # present | empty | not_applicable
interim_period_end, interim_fiscal_period, interim_accession_number
decision_contract_version
decision_watermark_identity  # duplicated on every row
```

**19-key vector** (`PURE_SEC_FEATURE_KEYS`): `revenue`, `gross_profit`,
`ebitda`, `ebit`, `net_income`, `eps_diluted`, `total_assets`,
`total_liabilities`, `total_equity`, `cash_and_equivalents`, `total_debt`,
`operating_cash_flow`, `free_cash_flow`, `gross_margin`, `ebitda_margin`,
`net_margin`, `roe`, `roa`, `roic`. Gold `return_on_equity` /
`return_on_assets` bind to `roe` / `roa`. Null stays null (null ≠ zero).

Snowflake SQL sketch (`01_subject_feature_screen.sql`) is the **relational
equivalent**: one view row per CIK, FY/interim metrics as **columns**
(`fy_revenue`, …), not nested vectors. SQL `03` issuer bundle is identity +
those feature-screen columns; it has **no neighborhood sections**. Python
is the nested document spec; SQL is flatter.

Live universe scale used for BSON math (not a Decision Subject Universe
snapshot — ticket 04 unpublished): MDM-active **63,197** CIKs
([v1 inputs research 07](../../agent-decision-v1-inputs/research/07-why-financial-factors-21-ciks.md);
[contract research 01](../../agent-decision-contract/research/01-live-decision-contract-objects.md)).
Gold `FINANCIAL_FACTORS` is still only **21** CIKs, so a live screen today
would be ~21 `present` FY rows and tens of thousands of `unavailable`.

### `decision_contract.py` — version, grade, watermark

`DECISION_CONTRACT_VERSION = "1"` (string). CONTEXT allows integer or
major.minor; first published Snowflake contract is version 1.

`evaluate_agent_grade(components) → AgentGradeResult`:

- `agent_grade: bool`
- `decision_contract_version: str`
- `watermark: DecisionWatermark` (always attached for audit)
- `reasons: tuple[str, ...]`

Required identity for grade: non-empty `business_date`, `gold_run_id`,
`graph_generation_id`; `silver_completeness_ok` and `graph_parity_ok`
true; high-severity reconcile blocks unless waived; bronze hashes required
iff `bronze_persist_used`.

`DecisionWatermark.to_dict()` / `AgentGradeResult.to_dict()` are JSON-serializable.
Snowflake READY is a **different field**:
`DECISION_CONTRACT_PUBLICATION.PUBLICATION_STATUS = 'ready'` plus
`ALIGNMENT_STATUS = 'aligned'`, `COVERAGE_STATE IN ('complete','partial')`,
and `GRAPH_ACTIVE_POINTER.ACTIVE_GENERATION_ID` match
(`03_dashboard_contract.sql`). Display uses `READINESS_STATE`
`agent_ready` | `not_ready`. Python bundles expose `agent_grade`, not
`PUBLICATION_STATUS`.

---

## BSON 16 MiB: Feature Screen cannot be one document

Official limit: **maximum BSON document size is 16 mebibytes**
([MongoDB Limits — BSON Documents](https://www.mongodb.com/docs/manual/reference/limits/#bson-documents)).
`_id` may be any type except array or regex; field names cannot contain
NUL; nesting ≤ 100.

`build_subject_feature_screen` returns **one dict** whose `rows` array
length equals `universe_size`. Measured compact JSON UTF-8 of the live
function (lower-bound proxy for BSON; BSON adds type tags):

| Payload | Bytes |
| --- | ---: |
| One populated per-CIK screen row | 1,187 |
| One unavailable per-CIK screen row (all-null vectors) | 1,165 |
| Screen envelope without `rows` | 241 |
| 63,197 populated rows (scaled) | ~71.5 MiB |
| 63,197 unavailable rows (scaled) | ~70.2 MiB |
| 16 MiB | 16,777,216 |
| Max populated rows that fit under 16 MiB | ~14,134 |

A naive `insert_one(build_subject_feature_screen(...))` for the MDM-active
set **cannot succeed**. v2 cannot persist the Python function return value
as one Mongo document. GridFS exists for oversized blobs; it is not a
Decision Graph Bundle shape and is not considered here.

A typical **issuer bundle** (empty or modest neighborhood) is a few KiB
and fits. A nested `holders_of_subject` / `subject_as_manager_portfolio`
section is a second size risk if a writer copied unbounded gold 13F rows
via `dict(r)` (gold `INSTITUTIONAL_HOLDINGS` is a large table; graph
`INSTITUTIONAL_HOLDS` is currently 97 edges). That is a collection-shape
input, not a lock.

---

## Collection-shape options (not chosen — grilling 04)

These are candidate BSON layouts of the **same** Python facts. No option
is recommended here.

### A. One collection, one document = one issuer bundle

Collection (name unset): documents ≈ `build_issuer_subject_bundle` return.
Neighborhood edges stay nested under `sections.*.rows`. Feature Screen is
**not** stored as the Python screen return. Ranking would either query
`sections.subject_features` across bundle docs, omit the screen, or be
left unspecified.

Fits BSON for typical issuers. Does not solve a 63k-row nested screen.
Does not by itself define a READY publication document.

### B. Envelope collection + per-row collections

Three (or four) collections, still projecting the Python dicts:

1. **Issuer envelope** — top-level keys + coverage flags +
   `sections.subject_features` + `sections.adv`; no large `rows[]`.
2. **Feature-screen rows** — one document per universe CIK = one element
   of `build_subject_feature_screen()["rows"]` (the 19-key vectors +
   coverage + duplicated watermark identity).
3. **Neighborhood edges** — one document per insider / employment /
   holder / auditor / parent row, with `bundle_subject_cik`, `section`,
   `relationship_type`, `agent_grade_edge`.
4. Optional **publication / watermark** singleton — Snowflake READY
   analogue (`PUBLICATION_STATUS`, pointer generation, coverage_state),
   not the Python bundle.

This is the shape that respects 16 MiB for the screen without pretending
the Python screen return is one document.

### C. Relational-mirror collections (SQL sketches as BSON)

Collections that look like `EDGARTOOLS_DECISION` objects rather than the
nested Python payload:

- `subject_feature_screen` — flat per-CIK columns as in
  `01_subject_feature_screen.sql`
- `subject_bundle_read_issuer` — identity + FY/interim columns as in
  `03_dashboard_contract.sql` (no neighborhood)
- `bundle_holders_of_subject`, `bundle_auditor` as in
  `02_subject_bundle_read_issuer.sql`
- extra collections for Python-only sections (`insiders`, `employment`,
  `has_parent`) that SQL sketches do not yet project

Client (or a later view) would **reassemble** `build_issuer_subject_bundle`
shape. Dual-layout risk vs the unit-tested Python spec.

Exact database/collection names and index DDL stay in this map’s
Not-yet-specified until grilling 04.

---

## JSON-writer seed analysis

**There is no persisted JSON agent SoE today.** Contract research 10
already recorded this; re-checked against the same modules.

| Writer | What it persists | Agent document? |
| --- | --- | --- |
| `JsonAlignmentStore` (`edgar_warehouse/serving/watermark_aggregator.py`) | Local file of `CauseAlignment` rows keyed by `cause_reference`: stage completeness, `gold_run_id`, `graph_generation_id`, `aligned`, SLO timestamps | **No.** Observe-only watermark rollup for `edgar-warehouse reconcile-decision-watermark --state-file`. Explicitly not `DECISION_CONTRACT_PUBLICATION` INSERT. Not a bundle, not a screen. |
| `SnowflakeTarget` / `default_serving_target()` (`serving/targets/snowflake.py`, `targets/base.py`) | Gold **Parquet** packages for Snowflake native S3 pull (`write_gold`, `write_ticker_reference`). Protocol has no `write_bundle`. `default_serving_target()` always returns `SnowflakeTarget`. | **No.** Warehouse serving export, not Decision Graph Bundles. |
| Streamlit Agent View (`infra/snowflake/streamlit/streamlit_app.py` `_render_agent_view_company`) | Reads `registered_query("agent.subject_bundle")` → `EDGARTOOLS_DECISION.SUBJECT_BUNDLE_DISPLAY_ISSUER` (**one relational row**, pandas DataFrame). Optional **CSV** download of that frame. | **No.** Human Audit View over Snowflake display objects. No JSON bundle persist. |
| `AGENT_VIEW_QUERIES` (`dashboard_query_registry.py`) | SQL against `DECISION_CONTRACT_DISPLAY_STATUS`, `DASHBOARD_SUBJECT_RESOLVER`, `SUBJECT_BUNDLE_DISPLAY_ISSUER` | Snowflake objects, not files |
| CLI `json.dumps` of watermark / parity | stdout diagnostics | Operator, not agent SoE |

Python dict builders remain the in-repo **shape specification**. Live
`EDGARTOOLS_DECISION` was empty when contract research 01 ran (zero
tables/views). Nothing in that gap is a Mongo collection.

A future Mongo writer would be a **new** serving-target implementation
(or a post-READY projector), not a reuse of `JsonAlignmentStore` or
`SnowflakeTarget`. Grilling 06 owns writer/READY timing; this ticket
only records that no seed writer exists.

---

## Identity keys a unique index would need

Fields that already identify an Agent-Grade payload, listed as **index
dimensions**, not as a chosen key:

| Dimension | Where it lives | Role |
| --- | --- | --- |
| CIK | `bundle_subject_cik` (int) / screen `rows[].cik` | Bundle Subject |
| Decision Contract Version | `decision_contract_version` (`"1"`) | Shape pin; agents pin a version |
| `agent_grade` | Python bool | Fail-closed trading-input flag; **not** unique by itself |
| READY | Snowflake `PUBLICATION_STATUS='ready'` + pointer join; display `READINESS_STATE` | Publication gate; **absent from the Python bundle dict** |
| `graph_generation_id` | watermark identity | Active graph pin; CONTEXT: pointer move fail-closes old READY |
| `business_date` | watermark identity | As-of business date |
| `gold_run_id` | watermark identity | Gold/feature as-of |

READY and `agent_grade` are related but not the same column. A unique
index might treat READY as a **partial-index filter** (only published
docs) rather than a key field. Historical watermarks vs “latest per CIK”
is unchosen.

**BSON `_id` options (not picked):**

1. CIK as BSON int (matches Python `int(subject_cik)`).
2. CIK as zero-padded 10-character string (SEC filing convention; not
   what the Python dict uses).
3. Compound `_id` document, e.g. `{cik, decision_contract_version,
   graph_generation_id}` or that set plus `business_date` / `gold_run_id`
   for multi-watermark history. `_id` may be an embedded document; it
   must not be an array.
4. Driver `ObjectId` plus a separate unique index on the identity
   compound.

MongoDB: `_id` is immutable, unique per collection, any type except
array/regex
([Restrictions on `_id`](https://www.mongodb.com/docs/manual/reference/limits/#mongodb-limit-Restrictions-on-_id)).

---

## ADR 0001 / CONTEXT delta for **v2** (v1 Snowflake stays)

Contract research 10’s v1 answer is reused, not reopened: **do not make
MongoDB the v1 Agent Decision Surface, instead of or beside Snowflake.**
This map is the “later serving-layer” door that research 10 parked.

**Quote — ADR 0001 locked table**
(`docs/adr/0001-agent-decision-surface-first.md`):

> | Delivery | Snowflake Decision Contract |

Header of the same ADR: agents still read **Snowflake only**. Unit of
read remains a Decision Graph Bundle rooted at CIK.

**Quote — product table**
(`docs/product-questions-and-dashboards.md`):

> **Agent delivery (v1)** | **Snowflake Decision Contract (A)** |
> Published Snowflake objects are the contract; audit UI reads the same;
> **S3/API optional later**

That last clause is the in-repo door for a later public serving layer.
It does not name MongoDB. v2 Atlas would be an instance of “optional
later,” not a v1 delivery change.

**Quote — CONTEXT Agent System of Engagement:**

> Snowflake Decision Contract objects only; agents never read silver or
> bronze directly.

**Quote — CONTEXT Snowflake Decision Contract avoid-list:** Streamlit-only
path, agent-private tables that diverge from audit UI, **S3 file dump as
the primary contract**.

Doctrine (`docs/doctrine-data-plane.md`): form trading decisions only
from aligned **Snowflake** projections. Trading-agent SoE row is
Snowflake Decision Contract, not Streamlit, silver, or bronze.

### What would have to be **added** (additive v2), not rewritten

ADR 0001 is accepted. Doctrine: do not re-introduce a superseded idea
without a **new** ADR. A v2 Mongo surface would need a new ADR (or an
explicit additive amendment) that says, in substance:

- v1 **Delivery remains** Snowflake Decision Contract.
- v2 is an optional internet-agent **projection** of the same Decision
  Graph Bundle / Feature Screen facts (same contract version, same
  watermark components, same READY/agent-grade gate), not a second SoE
  and not a warehouse ingest target.
- Human Audit View for v1 stays on Snowflake objects. A v2 Mongo copy
  must not become an agent-private table that diverges from audit UI
  (CONTEXT avoid-list). Dual-truth is the failure ADR 0001 rejected for
  UI-first.
- Auth for v2 is a later grilling item; ADR 0001 Deferred Access Control
  still applies to v1 Snowflake sessions.

CONTEXT would add a v2 term (internet serving surface / Mongo projection)
**under** Agent Decision Surface, without renaming Agent SoE off
Snowflake for v1. Product table would keep the v1 Snowflake row and
could name Mongo as one “S3/API optional later” instance.

**Would stay Snowflake even if v2 Mongo existed:** ingest (SEC →
edgartools → Bronze → Silver), gold dbt, graph Native App /
`GRAPH_ACTIVE_POINTER`, MDM Postgres, native S3 pull, SiS Agent View,
READY publication assertion. Agents.md AWS-only ingest path is
unchanged; Atlas is serving, not a second capture cloud.

This ticket does **not** propose replacing Snowflake as v1 Agent SoE.

---

## Confirm: no pymongo / Mongo / DocumentDB in repo or Terraform

Re-grep (this worktree, 2026-09-11):

| Surface | Result |
| --- | --- |
| `pyproject.toml` extras | `s3`, `snowflake`, `dashboard`, `mdm`, `mdm-runtime`, `market`. No mongo extra. No `pymongo` in dependencies. |
| `uv.lock` | no `pymongo` / `mongoengine` / `motor` / `mongodb` package name |
| `infra/terraform/**/*.tf` | no `mongodb`, `documentdb`, `atlas`, `mongo` resources |
| `infra/scripts` | no Mongo client or DocumentDB bootstrap |

Mongo is **not** in AWS Terraform and **must not** become a warehouse
ingest target (Agents.md: SEC → warehouse CLI → S3 bronze/warehouse →
Snowflake native pull → dbt gold). v2 Atlas, if later locked, is a
serving projection after READY, not bronze/silver/gold write.

---

## Sources

Primary (repo):

- `edgar_warehouse/serving/subject_bundle_read.py`
- `edgar_warehouse/serving/subject_feature_screen.py`
- `edgar_warehouse/serving/decision_contract.py`
- `edgar_warehouse/serving/watermark_aggregator.py` (`JsonAlignmentStore`)
- `edgar_warehouse/serving/targets/{base,snowflake}.py`
- `edgar_warehouse/serving/dashboard_query_registry.py`
- `edgar_warehouse/cli.py` (`reconcile-decision-watermark`)
- `tests/unit/test_subject_bundle_read.py`
- `tests/unit/test_subject_feature_screen.py`
- `infra/snowflake/sql/decision_contract/{01,02,03}_*.sql`
- `infra/snowflake/streamlit/streamlit_app.py`
- `docs/adr/0001-agent-decision-surface-first.md`
- `docs/adr/0002-silver-soe-edgartools-exclusive.md`
- `docs/doctrine-data-plane.md`
- `docs/product-questions-and-dashboards.md`
- `docs/subject-bundle-read.md`, `docs/subject-feature-screen.md`
- `CONTEXT.md` (Agent SoE; Decision Graph Bundle; Snowflake Decision Contract; Decision Watermark)
- `pyproject.toml`, `uv.lock`, `infra/terraform/`
- `.scratch/agent-decision-contract/research/10-json-mongodb-agentic-data-plane.md`
- `.scratch/agent-decision-v1-inputs/research/07-why-financial-factors-21-ciks.md` (63,197 MDM-active)

Official (size limit only):

- [MongoDB Limits and Thresholds — BSON Documents](https://www.mongodb.com/docs/manual/reference/limits/#bson-documents) (16 mebibytes)
