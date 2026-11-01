# Make catalog publication outcome explicit (PR #1261)

- [x] Reconcile PR branch against current `origin/main` and inspect the failing CI jobs — no-op rebase; both failures were stale GLEIF MapDoc target names, 2026-10-31 21:47 ET.
- [ ] Fix the GLEIF Mapping Document to agree with the configured `lei` target.
- [ ] Report catalog plan, publish and readback outcomes separately; keep plan side-effect free and check read-only.
- [ ] Cover successful readback, API rejection, partial publish, remote drift and output redaction; validate the final PR head with CI.
- [ ] Update the PR description and mark PR #1261 ready after required checks pass.
- [ ] Learning → skill: document publication status, readback scope and safe failure reporting in the catalog skills.
