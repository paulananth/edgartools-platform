# 02 — Prove one entity-facts window publishes

**What to build:** One `load_history` Stage 1B entity-facts window writes
companyfacts into canonical silver and landing without OOM. Operators can
see new financial-fact and derived rows for that window’s CIKs after the
run. This is the publish proof, not a redesign of the existing OOM
diagnosis.

**Blocked by:** None — can start immediately (parallel with 01).

**Status:** ready-for-agent

- [ ] One Stage 1B entity-facts window completes with a successful silver publish (not exit 137 in the publish step).
- [ ] Landing and collapsed silver gain financial-fact and derived rows for that window’s CIKs.
- [ ] Distinct fact CIKs in landing are greater than the Ticket 42 sample of 21, or the window is shown to contain only already-sampled CIKs and a second unused window is used instead.
- [ ] Gold facts/derived/factors for those new CIKs appear after the ordinary silver-landing and gold refresh path, or the ticket records the exact remaining refresh step.
