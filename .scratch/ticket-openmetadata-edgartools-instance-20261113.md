# Edgartools OpenMetadata local instance

## Checklist

- [ ] Add a separate OpenMetadata 2.0.7 Compose instance and keep the existing instance independent.
- [ ] Store the local login and verified PAT in the ignored `.env` with mode `0600`.
- [x] Update the OpenMetadata skill and token lifecycle instructions to use `.env`; genericity and guide-path checks passed (105 + 2 tests). 2026-11-13 13:06 ET
- [ ] Run required documentation checks, review the diff, and publish a PR.
- [ ] Learning → skill: document the pinned API login/PAT flow and strict separation of local instance data.
