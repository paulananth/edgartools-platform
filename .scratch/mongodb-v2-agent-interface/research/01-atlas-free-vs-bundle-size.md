# Atlas Free (M0) versus v2 agent document size

Ticket: `.scratch/mongodb-v2-agent-interface/issues/01-inventory-atlas-free-vs-bundle-size.md`

Date: 2026-09-11

Read-only. No Atlas provisioned. No live Snowflake dump. 21-CIK factor
coverage and ~63k MDM-active are reused from prior v1 input research, not
re-queried.

Does **not** reopen the v1 SoE verdict (Snowflake remains v1 Agent SoE;
Mongo is a later public serving layer). See
[agent-decision-contract research 10](../../agent-decision-contract/research/10-json-mongodb-agentic-data-plane.md)
and
[v1 free public DBs](../../agent-decision-v1-inputs/research/10-free-public-agentic-databases.md).

## Question

Can Atlas Free (M0) hold v2 agent documents for a realistic issuer set, or
does 512 MB / 500 connections / 100 ops/s / 10 GB week transfer force a
subset or a paid cluster before v2 is useful?

## Verdict

**M0 can hold a useful v2 of the 21-CIK sample, and can hold one document
per ~63k MDM-active issuer if most neighborhoods stay sparse (today’s live
coverage). It cannot hold 63k Apple-sized neighborhood documents in 0.5 GB,
and a single Feature Screen document for the universe would exceed the
server 16 MiB BSON limit (~82 MiB BSON measured).** Storage is not the
first reason to pay if v2 is one-doc-per-issuer; a universe-in-one-document
Feature Screen is illegal on every tier; 100 ops/s and 10 GB/7-day transfer
bite only if agents repeatedly scan the full set.

---

## Cited Atlas Free / M0 limits

Official Atlas name is **Free cluster** (formerly `M0`). Limits below are
from MongoDB docs, not blogs.

| Limit | Official value | Source |
| --- | --- | --- |
| Data storage | **0.5 GB** uncompressed BSON **plus indexes**. Not configurable. Commonly described as 512 MB; the table says 0.5 GB. **This is storage, not RAM.** | [Free cluster limits — Data Storage](https://www.mongodb.com/docs/atlas/reference/free-shared-limitations/) |
| RAM / memory | **Not published as a dedicated allotment.** “You can't configure memory for Free clusters.” Sort-in-memory cap **32 MB**. Aggregation `allowDiskUse` ignored (always false). | same page, Configuration Limits + Sort in Memory + Aggregation |
| Connections | **500** maximum | Operational Limits → Connections |
| Throughput | **100** read+write operations per second. Over limit: throttle network, 1 s cooldown per connection, queue-before-new. | Operational Limits → Throughput |
| Network transfer | **10 GB in and 10 GB out** per rolling **7-day** period. Same throttle/cooldown when exceeded. | Operational Limits → Data Transfer Limits |
| Free clusters per project | **One** (sales-contract exception only) | Configuration Limits + Operational Limits; also [MongoDB Limits — Free clusters per project = 1](https://www.mongodb.com/docs/manual/reference/limits/) |
| Never expires | Free clusters **never expire**; idle ones may **auto-pause after 30 days of zero connections** (Terms of Service; resume unless the paused version cannot restore). | [Deploy a Free Cluster](https://www.mongodb.com/docs/atlas/tutorial/deploy-free-tier-cluster/); Operational Limits → Cluster Persistence / Automatic Pause |
| Network peering | **Cannot** configure VPC/VNet peering | Configuration Limits |
| Private endpoints / PrivateLink | **Not supported** on Free | Configuration Limits |
| Backups | **Cannot** enable cloud backup; `mongodump`/`mongorestore` only (restricted options) | Configuration Limits |
| Databases / collections | **100** databases, **500** collections total | Operational Limits |
| Nested BSON depth (Free) | **50** levels (server-wide nested depth is 100) | Operational Limits; [BSON nested depth](https://www.mongodb.com/docs/manual/reference/limits/) |
| MongoDB version | Atlas runs **8.0**; you cannot pick/upgrade the version yourself | Configuration Limits |
| Auth methods on Free | Password (**SCRAM-SHA1** listed on Free limits), X.509, AWS IAM. Clients still need a **database user**. TLS cannot be disabled. | Operational Limits → Authentication; [FAQ: Security](https://www.mongodb.com/docs/atlas/reference/faq/security/) |
| Public hostname | Standard **`mongodb+srv://…mongodb.net`** only. `+srv` sets `tls=true`. **Do not hardcode cluster IPs** — they change (including on Free→M10 scale). Use SRV DNS. | [Connection string formats](https://www.mongodb.com/docs/manual/reference/connection-string-formats/); [FAQ: Networking](https://www.mongodb.com/docs/atlas/reference/faq/networking/); [mongosh connect](https://www.mongodb.com/docs/atlas/mongo-shell-connection/) |
| BSON document size | **16 mebibytes (16 MiB)** — **server limit on every tier, not an M0-only cap**. | [MongoDB Limits — BSON Document Size](https://www.mongodb.com/docs/manual/reference/limits/) |

512 MB in the ticket question is the **storage** figure (0.5 GB), not a
documented RAM budget. Atlas storage accounting is uncompressed BSON
documents **+ associated indexes**.

---

## In-repo payload shape (v2-relevant)

Canonical builders (Python dicts, JSON-serializable; not written to Mongo
today):

- `edgar_warehouse/serving/subject_bundle_read.py` →
  `build_issuer_subject_bundle`
- `edgar_warehouse/serving/subject_feature_screen.py` →
  `build_subject_feature_screen` (**one dict with `rows[]` for the whole
  universe**)
- `edgar_warehouse/serving/decision_contract.py` → watermark +
  `evaluate_agent_grade`

### Issuer Subject Bundle (one document per CIK)

Top-level keys from the builder:

`bundle_subject_cik`, `bundle_kind` (`issuer`),
`decision_contract_version`, `decision_watermark_identity`, `agent_grade`,
`agent_grade_reasons`, `include_neighborhood_history`, `sections`.

`sections` always includes:

| Section | v1 agent-grade? | Coverage when unbound |
| --- | --- | --- |
| `insiders` (`IS_INSIDER` + gold accession) | **yes** | `unavailable` if no graph/gold inputs |
| `employment` (`EMPLOYED_BY`) | **yes** | `unavailable` if no edges/pay |
| `subject_features` (FY + optional newer interim, 19 keys) | **yes** | FY `unavailable` / interim `not_applicable` if missing |
| `holders_of_subject` | **no** — stay on payload | `unavailable` on v1 |
| `subject_as_manager_portfolio` | **no** | `unavailable` on v1 |
| `auditor` | **no** | `unavailable` on v1 |
| `has_parent` | **no** | `unavailable` on v1 (incomplete inventory) |
| `adv` | n/a on pure issuer | always `not_applicable` |

CONTEXT: v1 Agent-Grade Input Facts are **features + current `IS_INSIDER` +
current `EMPLOYED_BY`**. Holders / auditor / parent remain unavailable, not
empty. That is the v2 document core this ticket sized.

### Watermark identity (on the bundle / screen, not the full dataclass)

`_watermark_identity` copies four fields only:

- `business_date`
- `gold_run_id`
- `graph_generation_id`
- `decision_contract_version`

The full `DecisionWatermark.to_dict()` also has `silver_completeness_ok`,
`graph_parity_ok`, bronze hashes, reconcile flags, notes. Those gate
`agent_grade` but are **not** in `decision_watermark_identity`.

`REQUIRED_COMPONENTS` for the grade: `business_date`, `gold_run_id`,
`graph_generation_id`, `silver_completeness_ok`, `graph_parity_ok`.

### 19 `PURE_SEC_FEATURE_KEYS`

`revenue`, `gross_profit`, `ebitda`, `ebit`, `net_income`, `eps_diluted`,
`total_assets`, `total_liabilities`, `total_equity`,
`cash_and_equivalents`, `total_debt`, `operating_cash_flow`,
`free_cash_flow`, `gross_margin`, `ebitda_margin`, `net_margin`, `roe`,
`roa`, `roic`.

No prices / PE / market cap (`FORBIDDEN_MARKET_FIELDS`). Null ≠ zero.

### Feature Screen is one dict for the universe

`build_subject_feature_screen` returns **one** payload:

`decision_contract_version`, `agent_grade`, `agent_grade_reasons`,
`decision_watermark_identity`, `universe_size`, **`rows[]`** (one element
per universe CIK, even when features are unavailable).

Each row embeds the 19-key FY vector, optional interim vector, coverage
flags, period metadata, and a **copy of the watermark identity**. That
repeated watermark is why a universe-in-one-document is large, and why it
matters for the 16 MiB cap.

---

## Measured byte sizes

Cheap measurement: `uv run python` imported the real builders in this
worktree, built a **synthetic Apple-like** issuer (CIK `320193`, 20
agent-grade insider rows, 30 `EMPLOYED_BY` rows, 8 executive-pay sidecar
rows, FY + newer Q1 19-key vectors), then `json.dumps(...,
separators=(',', ':'))` UTF-8 bytes. BSON size is a cross-check via
transient `pymongo.bson.BSON.encode` (not a repo dependency). Atlas
storage uses uncompressed BSON, so BSON is the closer storage proxy;
`json.dumps` is the ticket-required figure.

Holders / auditor / parent were **not** populated (v1 `unavailable`).
Numbers are synthetic; not a live gold dump.

| Object | JSON UTF-8 bytes | BSON bytes |
| --- | ---: | ---: |
| Full issuer bundle (all 8 sections; holders/auditor/parent `unavailable`) | 12,527 | 13,013 |
| **v2-shaped issuer doc** (identity + watermark + features + 20 insiders + 30 employment) | **11,992** | **12,471** |
| Same bundle, features only (no people) | 2,291 | 2,125 |
| One Feature Screen **row** (FY+interim 19-key, watermark copy) | 1,533 | 1,354 |
| Feature Screen dict, **21 CIKs** (real builder) | 32,545 | 28,821 |
| Feature Screen envelope (`rows=[]`) | 308 | 313 |
| Feature Screen dict, **63,000 rows in one document** (same row shape, unique `cik`) | **96,694,201 (~92.2 MiB)** | **85,732,203 (~81.8 MiB)** |

16 MiB = 16 × 1024 × 1024 = **16,777,216** bytes.

One insider row sample (builder output):
`person_entity_id`, `person_name`, `relationship_type=IS_INSIDER`,
`source_accessions[]`, `agent_grade_edge`.

One employment row sample: `person_entity_id`, `person_name`, `role_title`,
`source_system` (`proxy_def14a` / `item_5_02`), `relationship_type=EMPLOYED_BY`,
`effective_date`.

---

## Capacity math (21 vs ~63k)

Storage budget: **0.5 GB**. Use **512 MiB = 536,870,912 bytes** as the
generous reading of “0.5 GB / 512 MB”, and **500,000,000 bytes** as the SI
reading. Indexes are **inside** that budget. Index overhead is a **range,
not a precise percent**: a unique `_id` plus one `{cik, watermark}` unique
index on small documents is often on the order of **~15–40%** extra
uncompressed bytes (key size, WiredTiger leaf overhead, plus a second
index if READY/generation is indexed). Do not treat a single percentage as
measured.

### 21 sample CIKs (Apple + Ticket 42 sample)

Live gold `FINANCIAL_FACTORS` is **21 distinct CIKs** (Apple `320193` smoke
2026-07-29 + Ticket 42 20-CIK sample 2026-08-04/05). Source:
[v1 research 07](../../agent-decision-v1-inputs/research/07-why-financial-factors-21-ciks.md).

At the Apple-like v2 BSON size (12,471 B):

- 21 × 12,471 = **261,891 B ≈ 0.25 MiB** documents
- +15–40% indexes → **~0.3–0.4 MiB**

Feature Screen as **one 21-row document**: 28,821 B BSON — trivial versus
16 MiB and versus 0.5 GB.

**21-CIK v2 fits on M0 with orders of magnitude of headroom.** Ops/s and
transfer are irrelevant at this scale.

### ~63k MDM-active (ballpark, not a live query)

Prior live count: **63,197 MDM-active companies** versus 21 fact CIKs
(same research 07). Gold `COMPANY` was 73,691. CONTEXT Decision Subject
Universe is warehouse-active ∩ MDM-active; this ticket uses **~63k** as
the MDM-active ballpark already recorded, not a new `snow sql`.

**A. Sparse (matches current live neighborhood coverage)**

Live graph (v1 research 02/03, generation `ae0db138-…`): `IS_INSIDER`
present-capable on **87** MDM-active issuers; `EMPLOYED_BY` on **1,351**.
Features published for **21**. Most of 63k would be empty-neighborhood
docs (~2.1 KiB BSON).

Conservative mix: 1,351 Apple-sized v2 docs + remainder features-only:

- 1,351 × 12,471 + 61,846 × 2,125 ≈ **148 MiB** BSON
- +15–40% indexes → **~170–210 MiB**

**Fits in 0.5 GB.** Transfer for one full read ≈ 0.15–0.2 GB out of 10 GB
week.

**B. Dense (every issuer looks like the 20-insider / 30-employment Apple fixture)**

- 63,197 × 12,471 ≈ **788 MiB** BSON documents alone
- +15–40% indexes → **~0.9–1.1 GB**

**Does not fit.** ~43k Apple-sized docs fill 512 MiB with **no** index
headroom (536,870,912 / 12,471 ≈ **43,000**); ~31k–37k with 15–40%
indexes. 63k dense issuer documents need a **paid cluster** (or a much
smaller neighborhood, or omitting people from the default doc).

**C. Headcount only (ignore density)**

| Set | Docs at 12.5 KiB BSON, no indexes | vs 0.5 GB |
| --- | ---: | --- |
| 21 | 0.25 MiB | fits |
| ~43k Apple-sized | ~512 MiB | at the cap |
| 63,197 Apple-sized | ~751 MiB | **over** |
| 63,197 empty-neighborhood | ~128 MiB | fits |

### Throughput / transfer (why storage is not the only M0 question)

- **100 ops/s:** 63k point-reads at one `find` per CIK ≈ **10.5 minutes**
  if saturated. Fine for 21; painful for a naive full-universe poll loop.
- **10 GB in + 10 GB out / 7 days:** one sparse 63k read is well under.
  Re-reading 63k × 12.5 KiB **~13 times/week** approaches the 10 GB **out**
  cap. A chatty agent is the transfer risk, not the 21-CIK demo.
- **500 connections:** not the binding constraint for a handful of public
  agents.
- **30-day idle pause:** a public demo cluster with no traffic pauses;
  resume is documented, but an unattended agent would see a down window.

---

## 16 MiB Feature Screen warning

`build_subject_feature_screen` returns **one dict whose `rows[]` is the
whole universe.** That is a single BSON document if stored as-is.

| Universe | BSON of one Feature Screen document | vs 16 MiB |
| --- | ---: | --- |
| 21 CIKs | 28,821 B (0.027 MiB) | OK |
| ~12.4k full FY+interim rows | ≈ 16 MiB | **at the server cap** ((16,777,216 − 313) / 1,354 ≈ **12,387** rows) |
| 63,000 rows | **81.8 MiB BSON / 92.2 MiB JSON** | **~5.1× over 16 MiB** |

**A single Feature Screen document for ~63k MDM-active issuers cannot be
inserted on M0 or on a paid cluster.** The 16 MiB limit is a mongod
server limit, not an Atlas Free extra.

v2 implication (for later collection-shape tickets, not decided here):
Feature Screen must be **one document per CIK** (or chunked pages), not
one universe document. Per-row BSON ~1.4 KiB × 63,197 ≈ **82 MiB of many
small docs**, which **does** fit in 0.5 GB as a collection (indexes extra)
even though it is illegal as one document.

---

## Public-network path (`0.0.0.0/0` + TLS + DB user)

**Yes — that is the documented public-agent path on Free.** Peering and
PrivateLink are unavailable, so clients must use the **standard public
SRV hostname**.

Required pieces (official):

1. **IP access list** — Atlas “only allows client connections to the
   cluster from entries in the project's IP access list.” Add the agent
   IP **or** CIDR `0.0.0.0/0`.
2. **TLS** — required on all Atlas clusters; **cannot be disabled**.
   Free also requires the **SNI** TLS extension. `mongodb+srv://` sets
   `tls=true`. TLS 1.2 / 1.3 only.
3. **Database user** (SCRAM password on Free; distinct from Atlas UI
   users). Connect dialog creates one if missing.

`0.0.0.0/0` warnings (same official IP-access-list page):

- Adding `/0` (e.g. `0.0.0.0/0`) **“allows access from anywhere.”**
- Atlas **warns** this can expose the deployment to unauthorized access /
  exfiltration; **restrict when possible** and **use strong credentials**
  for all database users when allowing public Internet access.
- Adding any IPv4 `/0` CIDR **emails an alert** to every user with a
  project role (direct or via team).

Do **not** hardcode cluster node IPs. FAQ: Networking: public IPs change
(scale Free→M10, region change, etc.); use **SRV**. Firewall allowlists
that need IPs must refresh via the Atlas “Return All IP Addresses”
API — documented as dynamic.

This matches the v1 free-public-DB note: allowlist the agent IP **or**
`0.0.0.0/0`; M0 is the only perpetually free public hostname of the three
vendors. It does not change ADR 0001’s v1 Snowflake SoE.

---

## Practical answer for v2

| v2 shape | M0 useful? |
| --- | --- |
| 21-CIK issuer documents (features + insiders + employment + watermark) | **Yes**, trivially. |
| ~63k one-doc-per-issuer, **sparse** neighborhoods (today’s live graph/features) | **Yes**, ~0.15–0.2 GB + indexes. |
| ~63k one-doc-per-issuer, **Apple-dense** neighborhoods | **No** — ~0.75–1.1 GB. Subset or paid. |
| Feature Screen as **one universe document** | **No on any tier** (81.8 MiB > 16 MiB). |
| Feature Screen as **one doc per CIK**, 63k rows | Storage **fits**; do not wrap them in one parent document. |
| Chatty full-universe polling | 100 ops/s and 10 GB/week become the limit before RAM (unpublished). |

**Paid cluster is not a prerequisite for a useful v2** of the known 21-CIK
factor set, nor for a sparse MDM-active collection. Paid (or a deliberate
subset / slimmer neighborhood) **is** required before treating “every
MDM-active issuer looks like Apple’s insider/employment fixture” as the
default document. Do not store Feature Screen as a single universe
document.

---

## Sources

Official MongoDB (not blogs):

- https://www.mongodb.com/docs/atlas/reference/free-shared-limitations/
- https://www.mongodb.com/docs/atlas/tutorial/deploy-free-tier-cluster/
- https://www.mongodb.com/docs/atlas/security/ip-access-list/
- https://www.mongodb.com/docs/atlas/mongo-shell-connection/
- https://www.mongodb.com/docs/atlas/connect-to-database-deployment/
- https://www.mongodb.com/docs/atlas/reference/faq/networking/
- https://www.mongodb.com/docs/atlas/reference/faq/security/
- https://www.mongodb.com/docs/atlas/security-add-mongodb-users/
- https://www.mongodb.com/docs/manual/reference/limits/ (BSON 16 mebibytes)
- https://www.mongodb.com/docs/manual/reference/connection-string-formats/

In-repo:

- `edgar_warehouse/serving/subject_bundle_read.py`
- `edgar_warehouse/serving/subject_feature_screen.py`
- `edgar_warehouse/serving/decision_contract.py`
- `docs/subject-bundle-read.md`, `docs/subject-feature-screen.md`
- `CONTEXT.md` (Trading-Relevant Neighborhood; v1 Agent-Grade Input Facts;
  Bundle Coverage Flags; Decision Subject Universe)
- `tests/unit/test_subject_bundle_read.py`,
  `tests/unit/test_subject_feature_screen.py`

Prior research (reused, not reopened):

- `.scratch/agent-decision-v1-inputs/research/10-free-public-agentic-databases.md`
- `.scratch/agent-decision-v1-inputs/research/07-why-financial-factors-21-ciks.md` (21 CIKs; 63,197 MDM-active)
- `.scratch/agent-decision-v1-inputs/research/02-is-insider-input-completeness.md`
- `.scratch/agent-decision-v1-inputs/research/03-employed-by-input-completeness.md`
- `.scratch/agent-decision-contract/issues/10-json-mongodb-as-agentic-data-plane.md`
- `.scratch/agent-decision-contract/research/10-json-mongodb-agentic-data-plane.md`
