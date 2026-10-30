# Preserve selected-engine control and Journal recovery guidance

Status: guidance and local review qualified; publish with the implementation dependency and require current-head CI before readiness/merge.
Base: b05d27513; branch codex/bookkeeping-portability-skill-20261030.
Implementation dependency: PR #1237, source head 6b057fc8. Publish for review in
parallel, but merge this guidance only after that implementation lands. The
database-name flags and missing-history guard belong to that implementation.

- [x] Update Bookkeeping initialization, duty-grant and recovery guidance for its qualified PostgreSQL/MySQL control path; retain SQL Server's deferred normal lifecycle — 2026-10-30 06:57 ET: independent review confirmed the actual configured/runtime boundaries.
- [x] Document the existing Journal selected-engine boundary, explicit database-name flag and refusal to recreate missing initialized event history — 2026-10-30 06:57 ET: checked against implementation source 6b057fc8; normal and independent installed cases pass on both selected engines.
- [x] Verify source neutrality, command construction, links, Standards/Spec/GoF and whitespace — 2026-10-30 06:57 ET: 95 affected checks passed; both independent reviewers found no remaining issue after verifying the implementation dependency. No links were added.
- [ ] Publish a separate guidance PR, retain its implementation dependency and require green final-head CI before readiness/merge.
- [x] Learning → skill: bookkeeping and change-journal, selected-engine owner installation and recovery boundaries — 2026-10-30 06:57 ET: configured database/driver, membership-only profile groups, host-restricted accounts, interrupted install recovery, and explicit lost-history/legacy-guard refusals.
