# Make catalog publication outcome explicit (PR #1261)

- [x] Reconcile PR branch against current `origin/main` and inspect the failing CI jobs — no-op rebase; both failures were stale GLEIF MapDoc target names, 2026-10-31 21:47 ET.
- [x] Fix the GLEIF Mapping Document to agree with the configured `lei` target — regenerated with canonical `mapdoc.write`; MapDoc checks pass, 2026-10-31 22:26 ET.
- [x] Report catalog plan, publish and readback outcomes separately; keep plan side-effect free and check read-only — implementation compiled and 47 focused catalog/MapDoc tests pass, 2026-10-31 22:57 ET.
- [x] Preserve missing-configuration CLI behavior — exit code 2 and required variable names; regression covered by 47 focused tests, 2026-10-31 22:57 ET.
- [x] Cover successful readback, API rejection, partial publish, remote drift and output redaction — 47 focused catalog/MapDoc tests pass, 2026-10-31 22:57 ET.
- [ ] Validate the final PR head with CI.
- [x] Update PR #1261 description — includes implementation and current validation status, 2026-10-31 22:57 ET.
- [ ] Mark PR #1261 ready after required checks pass.
- [x] Learning → skill: document publication status, readback scope and safe failure reporting in `skills/data-catalog/SKILL.md` and `skills/openmetadata/SKILL.md`; genericity (93) and guide-path (2) checks pass, 2026-10-31 22:26 ET.
