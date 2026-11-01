# Make catalog publication outcome explicit (PR #1261)

- [x] Reconcile PR branch against current `origin/main` and inspect the failing CI jobs — no-op rebase; both failures were stale GLEIF MapDoc target names, 2026-10-31 21:47 ET.
- [x] Fix the GLEIF Mapping Document to agree with the configured `lei` target — regenerated with canonical `mapdoc.write`; MapDoc checks pass, 2026-10-31 22:26 ET.
- [x] Report catalog plan, publish and readback outcomes separately; keep plan side-effect free and check read-only — implementation compiled and 46 focused catalog/MapDoc tests pass, 2026-10-31 22:26 ET.
- [ ] Cover successful readback, API rejection, partial publish, remote drift and output redaction; validate the final PR head with CI.
- [ ] Update the PR description and mark PR #1261 ready after required checks pass.
- [x] Learning → skill: document publication status, readback scope and safe failure reporting in `skills/data-catalog/SKILL.md` and `skills/openmetadata/SKILL.md`; genericity (93) and guide-path (2) checks pass, 2026-10-31 22:26 ET.
