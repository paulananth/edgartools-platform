# Inventory data not available to agents

Type: research
Status: resolved
Blocked by: none

## Question

Besides the issuer v1 agent-grade set (As-Of Decision Features, `IS_INSIDER`,
`EMPLOYED_BY`) and the keys already locked `unavailable` (holders, auditor,
parent, issuer ADV `not_applicable`), what other data exists in prod gold /
graph / source that a trading agent **cannot** read as an Agent-Grade
Decision Contract input?

Bucket each item as:

1. **Contract policy** — out of v1 Agent Decision Surface (ADR 0001 / this
   map's Out of scope).
2. **Locked unavailable** — on the issuer bundle, not Trading Decision input.
3. **Live empty or unbound** — table or graph type exists but rows/bind fail.
4. **Explore-only** — gold exists; Agent View allowlist forbids it.
5. **Not published** — contract objects / READY / universe snapshot missing.

Cite live `COUNT(*)` or in-repo allowlists. Do not implement.

Save findings at
`.scratch/agent-decision-contract/research/13-data-not-available-to-agents.md`.

## Answer

Live 2026-09-11. Full buckets:
[research/13-data-not-available-to-agents.md](../research/13-data-not-available-to-agents.md)

Nothing is agent-grade in prod today (`EDGARTOOLS_DECISION` empty, no
READY). Beyond v1 issuer sections (features, `IS_INSIDER`, `EMPLOYED_BY`):
holders/auditor/parent stay unavailable; prices/ADV-manager/filing-text
are policy-out; most gold (facts, filings, 13F, earnings, funds) is
Explore-only; consensus/guidance/transcripts/calendar are empty; graph
`MANAGES_FUND` is large but out of this map.

## Comments

- 2026-09-11 continuation: live gold still lacks `EBITDA`/`EPS_*` columns
  and 13F `ISSUER_CIK`; silver still holds 59k ownership-owner rows and
  14k 13F filings that the contract cannot see; graph has 130k fund /
  24k adviser nodes outside issuer v1. See research §7.
- 2026-09-11 full schema sweep: gold `ADV_FUND_COUNT_RECONCILIATION` +
  `MDM_*` entity tables; silver attachments/raw objects/ADV filings;
  `SEC_FILING_TEXT` 0; `IS_PERSON_OF`/`AUDITFIRM` 0; 20 graph generations
  stored; two Streamlit apps, empty Decision schema. See research §8.
- Bookkeeping Postgres and bronze S3 are **out of scope for agents**
  (ADR 0001). This inventory does not cover them.
