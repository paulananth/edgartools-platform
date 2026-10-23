# Document MDM destination-authority learning

Depends on code PR #1148; this branch changes guidance only.

- [x] Document commit-lifetime authority, retry identity, explicit input publication and derived-route reindexing in the owning skill reference — compared with PR #1148 implementation; 2026-10-23 13:05 ET.
- [x] Verify guidance against the protocol-4 implementation and real-engine outcomes; check source neutrality and local links — PostgreSQL/MySQL checkpoint outcomes compared with the API and SQL, seven skill-neutrality cases passed; 2026-10-23 13:05 ET.
- [x] Review Standards, Spec and GoF, pass the overlap guard, and create the separate skill PR — review below, overlap/whitespace checks pass, PR #1150 created; 2026-10-23 13:08 ET.
- [x] Verify final CI; retain an explicit named merge gate — all nine checks passed at dc740a7f; operator explicitly approved #1150, then merge acd96aa8 verified; 2026-10-23 13:23 ET.
- [x] Learning → skill: `mdm-engineering/references/storage-adapters.md`, worker authority and input-publication section; seven genericity cases passed; 2026-10-23 13:05 ET.


## Review

### Standards

Fresh isolated branch from origin/main; guidance only and no source values.
Shared skill changes are separate from engine implementation. Link targets
remain unchanged and the source-neutrality cohort passes seven cases.

### Spec

Documents opt-in protocol 4 as a PostgreSQL/MySQL helper capability and retains
the explicit missing normal-worker integration. SQL Server remains deferred.
Retry authority, commit expiry and input/index publication have distinct proofs.

### GoF

No code or interface change. The guidance keeps the existing storage adapter
and shared native computation, with no second merge algorithm or hierarchy.
