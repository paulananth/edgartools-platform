# Load Person into shared local PostgreSQL

Status: blocked before submission. Operator request: "run person load to the new postgress infr".

## Checklist

- [x] Isolate operational work from protected main and other runtimes. Verified dedicated `codex/person-shared-load-20261017` worktree at merged main `272f60a0`; primary checkout unchanged. 2026-10-17 09:09 ET.
- [x] Check existing shared PostgreSQL and source lifecycle. Read-only queries: Person source and platform merge policy each have one draft, zero recorded tests and zero approvals; MDM has zero datasets, mappings, policies, runs and Person masters; Bookkeeping has zero runs. 2026-10-17 09:09 ET.
- [x] Exercise the real Rules resolver with the shared runtime connection. It refuses Person with `No active proven Rules version; authoring files cannot be executed`. No submission or database mutation. 2026-10-17 09:09 ET.
- [x] Locate complete retained capture without provider access. Full capture contains 76,231 distinct receipt entries, including 76,230 CIK-path entries; the overlapping smaller capture must not be added to the full population. Receipt inventory only: content hashes, completeness and Person outcomes are not yet verified by this task. 2026-10-17 09:09 ET.
- [ ] Resolve local-capture registration/activation gap through the supported Rules lifecycle. Current Person source has no acquisition section; `Rules.activate` refuses an MDM source without approved acquisition authority even after test/approval. Existing source-readiness requirements permit genuine retained-capture qualification, but that path still needs implementation. Do not fake authority or register through fixture helpers. Existing activation backlog includes Person in rebuild ticket 71; the local gap is separate from AWS deployment.
- [ ] Record genuine evidence for the exact Person source and merge policy, and satisfy their supported lifecycle. The request to load is not fabricated approval evidence for an untested version.
- [ ] Process the whole retained delivery through read, prepare, merge and Journal recording, with separate verification and finalization. No sample load substituted.
- [ ] Reconcile accepted/waiting/rejected records; repeat identical inventory and prove zero selected files and no new mastering run.
- [x] Learning → skill: none. Existing `data-platform` Source readiness rules already require genuine provenance and the normal lifecycle; this is an implementation gap, not a new policy. 2026-10-17 09:09 ET.

## Boundaries and evidence

No provider requests, downloads, source activation, shared migrations, shared writes or load occurred. The server was not stopped, reset or replaced. All checks used the existing private connection files without displaying credentials or source records.

GitHub was unavailable during this attempt: `git fetch origin main` failed to connect to github.com port 443 after 67,576 ms; `gh auth status --hostname github.com` timed out. Used the already verified merged `origin/main` revision `272f60a0`; no claim that it remained the latest remote revision. No commit, push or PR attempted.
