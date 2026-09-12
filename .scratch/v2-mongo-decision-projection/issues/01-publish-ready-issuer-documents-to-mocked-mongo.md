# 01 — Publish READY issuer documents to a mocked Mongo

**What to build:** After the Snowflake Decision Contract is READY, a
publisher upserts one Subject Bundle Read and one Subject Feature Screen
document per Bundle Subject into `edgartools_decision`, matching the
accepted Mongo Decision Projection data contract (full Decision Watermark,
`readiness_state`, `_id` = int CIK). If publication is not READY or the
watermark is not agent-grade, it writes nothing agent-grade. Proven with a
mocked store in unit tests — no Atlas.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [x] READY + agent-grade watermark writes one `issuer_subject_bundle` and one `subject_feature_screen` document per CIK
- [x] Documents carry full watermark (including bronze digest when bronze persist was used), `readiness_state=agent_ready`, `projected_from=snowflake_decision_contract`
- [x] Bundle keeps the Python envelope (unavailable stubs / ADV `not_applicable`)
- [x] Feature Screen is one row document, not the universe payload
- [x] Not READY or not agent-grade writes zero documents
- [x] Tests inject a mocked store; no Atlas, no CI secrets
