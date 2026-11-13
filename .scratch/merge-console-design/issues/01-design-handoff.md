# Shared mastering and policy console design

Type: task
Status: claimed

Deliver an implementer-ready design document using the vendor guidance, plus a UI for maintaining and visualizing Company, Person and Security flows. This task supplies the design, diagram and interactive prototype; the production service is implementation scope described by the handoff.

- [x] Verify current rule, merge, stewardship and UI boundaries against clean main `9b00663ad`; corrected an initial stale-checkout assumption about removed Rules lifecycle APIs (2026-11-13 07:38 ET).
- [x] Specify entity policy contracts, shared engine boundaries, proposed backend/UI contracts and acceptance in DESIGN.md; no retired lifecycle is assumed (2026-11-13 07:38 ET).
- [x] Build and validate the preserved proposed architecture HTML/JSON; Archify validate/deliver/check/browser-check all passed (2026-11-13 07:38 ET).
- [x] Build interactive UI prototype with local drafts and flow visualization; opened in Lavish with foreground feedback poll (2026-11-13 07:38 ET).
- [x] Check prototype interactions via Playwright, inspect light/dark and desktop/narrow captures; no page errors/overflow; documentation checks 107 passed in 0.49s (2026-11-13 07:38 ET).
- [x] Review Standards, Spec and GoF; no blocking findings; recorded in VERIFICATION.md (2026-11-13 07:38 ET).
- [ ] Publish the design and preserved assets in a PR.
- [x] Learning → skill: none changed in this design PR; current-code ownership is applied. DESIGN.md slice 0 explicitly requires reconciling stale command references before implementation (2026-11-13 07:38 ET).
