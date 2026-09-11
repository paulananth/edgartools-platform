# Lock issuer v1 agent-grade bundle sections

Type: grilling
Status: resolved
Blocked by: 01, 02, 08

## Question

Which issuer Subject Bundle Read sections are agent-grade in v1, and which
are display-only or omitted, given live gold/source/silver tables?

At minimum decide presence, empty, unavailable, or not_applicable for:

- As-Of Decision Features (FY + optional interim)
- IS_INSIDER (graph + gold ownership accessions)
- HOLDS / holders_of_subject and subject_as_manager_portfolio
- EMPLOYED_BY
- AUDITED_BY
- HAS_PARENT
- ADV (must remain not_applicable for pure issuers)

Predecessor: [Subject Bundle Read issuer](../../agent-decision-data-plane/issues/11-subject-bundle-read-issuer.md)
is closed as product shape; this ticket binds that shape to tables that
actually exist after ADR 0006 and current gold/source wiring.

## Comments

- 2026-09-10: rebased `grok/agent-decision-data-plane-wayfinder` onto
  `origin/main` `ea9fadbb` (PRs #581/#582). Live neighborhood counts
  refreshed against generation `ae0db138-...` (233,647 nodes / 575,485
  edges). See
  [research/11-refresh-neighborhood-counts.md](../research/11-refresh-neighborhood-counts.md).
  Q1 not yet answered; recommendation updated for `EMPLOYED_BY` 3 → 4,313.
- Q1 (2026-09-10): v1 agent-grade sections are **As-Of Decision Features + `IS_INSIDER` + `EMPLOYED_BY`**. Holders, auditor, and parent stay on the payload as unavailable / display-only. ADV remains `not_applicable`.
- Q2 (2026-09-10): `holders_of_subject`, `subject_as_manager_portfolio`, `auditor`, and `has_parent` are **`unavailable`** (keys kept, no agent-grade rows, not `empty`, no unbound 6.8M gold dump). ADV remains `not_applicable`.
- Q3 (2026-09-10): empty/unavailable on an agent-grade section is **section flag only**. Bundle agent-grade still follows watermark + non-empty universe. Empty insiders ≠ failed contract.
- Q4 (2026-09-10): `IS_INSIDER` is graph-keyed. `present` = ≥1 current edge with source accession; `empty` = zero current edges after a complete snapshot; `unavailable` = bind failed or inputs missing. Gold-only strings are never `present`.
- Q5 (2026-09-10): `EMPLOYED_BY` is graph-keyed with source `proxy_def14a` or `item_5_02`. Pay-only gold rows are `non_agent_grade`, not `empty` or `present`.
- Q6 (2026-09-10): Feature coverage matches glossary/Python. FY present/empty/unavailable; interim present or `not_applicable`; interim does not require FY; all-null is `empty`. Gold column aliases for the v1 vector are a follow-up ticket.

## Answer

v1 agent-grade issuer sections are **As-Of Decision Features**, **`IS_INSIDER`**, and **`EMPLOYED_BY`**. ADV stays `not_applicable`.

`holders_of_subject`, `subject_as_manager_portfolio`, `auditor`, and `has_parent` stay on the payload as **`unavailable`** (Ticket 11 keys kept; not `empty`; no unbound gold 13F dump). Live bind after generation `ae0db138-...`: employment graph 4,313; insiders 902; institutional holds 97 with no gold `issuer_cik`; auditor/parent evidence 0.

Section coverage does **not** fail bundle agent-grade (watermark + non-empty universe still govern).

| Section | `present` | `empty` | `unavailable` / other |
| --- | --- | --- | --- |
| `IS_INSIDER` | ≥1 current graph edge with source accession | snapshot complete, zero current edges | bind failed or inputs missing; gold-only names never present |
| `EMPLOYED_BY` | ≥1 current graph edge with source `proxy_def14a` or `item_5_02` | snapshot complete, zero current edges | bad/missing source or inputs missing; pay-only gold is `non_agent_grade` |
| Features FY | primary annual vector exists | snapshot complete, no FY vector | features not in snapshot; all-null is empty |
| Features interim | non-FY period_end after FY (or after nothing) | — | `not_applicable` if none newer; does not require FY |

Gold `FINANCIAL_FACTORS` key/alias mapping is [Lock v1 As-Of Decision Feature keys against gold](11-lock-v1-feature-keys-against-gold.md).
