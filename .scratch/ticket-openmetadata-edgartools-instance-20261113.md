# Edgartools OpenMetadata local instance

## Checklist

- [x] Install the separate OpenMetadata 2.0.7 Compose project; all 3 containers healthy and the prior project untouched (it now has 0 running containers). 2026-11-13 14:16 ET
- [x] Store local login and verified PAT in the ignored repository `.env`, mode `0600`; credential and version readback confirmed without printing values. 2026-11-13 14:16 ET
- [x] Update local endpoint and credential instructions in the OpenMetadata and connection skills; genericity and guide-path checks passed (107 total). 2026-11-13 14:16 ET
- [x] Make init clear AI Governance entities, including AI-specific intake forms and workflow definitions; rerun confirmed 0 active entities after soft-deleting the remaining workflow definition. 2026-11-13 14:16 ET
- [x] Publish and independently check the configured catalog: 8 domains, 8 glossaries, 31 terms, 71 assets, 2 configured quality definitions, 61 cases, 3 products, 82 pipelines, 14 PipelineServices and 145 lineage edges. 2026-11-13 14:16 ET
- [x] Read back product relations from the native API: all 3 products have domains, with 13 asset references and 10 input ports. 2026-11-13 14:16 ET
- [x] Publish current Snowflake Postgres Bookkeeping state to the latest 3 target Pipelines; all 3 native status readbacks confirmed (2 Pending, 1 Successful). 2026-11-13 14:16 ET
- [x] Check current per-load quality eligibility: none of the latest completed runs requested version-2 quality evidence; the flag remains unset, so no result was synthesized. 2026-11-13 14:16 ET
- [x] Run final checks and three-axis diff review; 107 documentation checks pass, Ruff/syntax checks pass, and init API readback confirms zero active AI entities. 2026-11-13 14:16 ET
- [ ] Commit and publish the updated draft PR; current-head CI gates merge.
- [x] Learning → skill: make full AI Governance cleanup a required, version-qualified OpenMetadata initialization step in `skills/openmetadata/SKILL.md` and `LOCAL-SERVER.md`. 2026-11-13 14:16 ET
