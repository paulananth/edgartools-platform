# ER dashboards — wayfinder map

Label: `wayfinder:map`  
Repo: **edgartools-platform**  
Consumers: financial-services equity-research skills / desk agents (Explore-first)

## Destination

A locked **ER dashboard design pack** for Streamlit-in-Snowflake: which screens to ship, how they map to the nine ER skills, which tables/modes they use (Agent View vs Explore + ERDP products), wireframe layouts, and a build order that does **not** rewrite skill bodies (C-06) and does **not** inject market/consensus into pure-SEC Agent-Grade features (ADR 0001 / ERDP-06).

Artifacts:

| Path | Role |
|------|------|
| [spec.md](./spec.md) | Product + UX design source of truth |
| [assets/skill-dashboard-map.md](./assets/skill-dashboard-map.md) | 9 skills × dashboard coverage |
| [assets/wireframes.md](./assets/wireframes.md) | ASCII layouts per dashboard |
| [assets/data-mode-matrix.md](./assets/data-mode-matrix.md) | Object allowlist / mode per widget |
| [issues/](./issues/) | Design decisions + future build tickets |

**Status: DESTINATION REACHED** (2026-07-25) — design locked; implementation tickets optional next.

## Notes

- **Domain:** Human Audit / research dashboards over gold + ERDP Explore products; same dual-mode chrome as existing SiS app.
- **Consult each session:** this map; `docs/adr/0001-agent-decision-surface-first.md`; `docs/product-questions-and-dashboards.md`; `docs/dashboard-agent-view-explore.md`; `docs/er-earnings-calendar.md`; `docs/er-market-eod-join.md`; `.scratch/er-data-plane/` (coverage matrix, HANDOFF).
- **Skill source of truth (read-only):** financial-services `plugins/vertical-plugins/equity-research/skills/` + `.scratch/er-data-plane/assets/er-skills-io.md` (copied inventory).
- **Completeness gate:** every ER skill has ≥1 primary dashboard path; every dashboard widget names mode + data object; P0 build set is ≤4 screens.
- **Relation to existing P0 UIs:** Company 360 / Screener / Insider Watch remain the accounting-first audit triad; ER dashboards **extend** them with desk workflows (earnings, catalysts, ideas) rather than replacing them.
- **Tracker:** local markdown under `.scratch/er-dashboards/`.

## Decisions so far

- **Repo of record** — Dashboard *design* lives here; financial-services owns skill prose (no body rewrites this effort).
- **Mode doctrine** — ER desk screens default to **Explore** (labeled); Agent View only for watermarked contract audit strips (bundle/screen/status). Market (ERDP-07), calendar (ERDP-03), future consensus/guidance/transcripts are Explore-only.
- [Confirm dashboard set vs skill map](./issues/01-confirm-dashboard-set.md) — **Four** primary ER dashboards: Earnings Desk, Catalyst Board, Research Workspace (Company 360 ER tabs), Idea & Sector Screen; Thesis is a panel, not a fifth app.
- [Agent View vs Explore placement](./issues/02-mode-and-data-boundaries.md) — Dual-mode chrome retained; ERDP products never Agent View Decision Features without new ADR.
- [Build order vs ERDP readiness](./issues/03-build-order-vs-erdp.md) — Ship P0 on gold + ERDP-03 + ERDP-07; stub consensus/guidance/transcript panels until ERDP-01/02/04 land.
- [Nav integration with existing SiS](./issues/04-sis-nav-integration.md) — Extend `infra/snowflake/streamlit/streamlit_app.py` nav: keep Summary / Company / Pipeline; add **Earnings · Catalysts · Ideas** under Explore; Research Workspace = enriched Company Details.
- Design pack published: [spec.md](./spec.md), [assets/](./assets/).

## Not yet specified

- Exact Streamlit multipage vs single-file tab implementation (build-time)
- Pilot CIK universe size for live demos
- Whether financial-services agent YAML links to dashboard URLs (post-build)
- Production SiS deploy ticket sequence (DASH-* in research doc vs new ERD tickets)

## Out of scope

- Rewriting financial-services ER skill SKILL.md bodies
- Injecting prices/consensus into pure-SEC `subject_features`
- Order execution / portfolio OMS / broker connectivity
- Street ratings history product (External)
- Full Platform Command Center rebuild (operator P2)
- Neo4j visual browser redesign (owned by MDM graph dashboard)
- Implementing ERDP-01/02/04 (owned by er-data-plane workstream)
