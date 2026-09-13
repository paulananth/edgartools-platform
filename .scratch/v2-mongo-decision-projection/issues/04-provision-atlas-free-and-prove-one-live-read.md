# 04 — Provision Atlas Free and prove one live read

**What to build:** Operator provisions Atlas Free (M0): database
`edgartools_decision`, two collections, `$jsonSchema`, `0.0.0.0/0` + TLS,
one read-only agent SCRAM user and a separate publisher write user. One
smoke publish; an internet-style find with the read-only user returns
agent-grade documents.

**Blocked by:** 03 — Run the publisher after the READY aggregator (for the live proof). Cluster signup can start in parallel with 01.

**Status:** ready-for-human

Operator path is in-repo (mocked tests + wizard). Live cluster checkboxes
stay open until a human runs the wizard against Atlas.

- [ ] M0 cluster exists with the accepted database and collections
- [ ] Read-only agent user cannot write
- [ ] Publisher write user can upsert
- [ ] One smoke publish; read-only find returns agent-grade docs

## Comments

- 2026-09-11 Implementation: `PyMongoDecisionStore` adapter (injected
  client; pymongo lazy), `$jsonSchema` + generation index,
  `run_mongo_decision_smoke` (publisher write / agent find / agent write
  rejected), operator wizard
  `infra/scripts/provision-atlas-decision-projection.sh` writing local
  `.env` only (no GitHub secrets). Run:
  `bash infra/scripts/provision-atlas-decision-projection.sh`
