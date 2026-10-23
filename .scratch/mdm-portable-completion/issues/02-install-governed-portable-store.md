# Install governed MDM storage on both engines

Type: task
Status: resolved
Assignee: Codex
Claimed: 2026-10-23 14:39 ET
Parent: [Complete portable MDM and retire PostgreSQL business logic](../map.md)
Blocked by: 01

## Question

Can the normal owner migration install and upgrade the same governed storage contract on PostgreSQL and MySQL?

## Parts

- [x] Connect the existing portable adapter to the normal MDM owner migration; retain immutable policies, dataset contracts, configured kind authority, version pins and runtime restrictions — normal-caller checks on PostgreSQL/MySQL, 2026-10-23 15:17 ET.
- [x] Preserve migration checksums and retained records; qualify populated upgrade, interruption, already-open runtime connections and repeat migration — shared governed-storage checks, including held MySQL transaction and prepared-store retention, 2026-10-23 15:17 ET.
- [x] Refuse missing or changed configuration, direct runtime governance writes and excess privileges; retain owner/runtime separation — real restricted-role and inherited column-grant checks, 2026-10-23 15:17 ET.
- [x] Qualify exact registry JSON values and reject an untracked or structurally changed registry; preserve all existing prepared-effect protocol fingerprints — exact-number, structural/guard drift, untracked-adoption, hash-seed and protocols 1–4 checks (SQL Server 1–3), 2026-10-23 15:17 ET.
- [x] Qualify the normal migration CLI and independently installed packaging for the new storage helper — five-wheel normal-owner proofs on both engines from committed implementation f44de352, 2026-10-23 15:17 ET.
- [x] Publish implementation and verify CI on its implementation revision; retain final landing-head checks and named merge approval as separate PR gates — PR #1152, all nine checks pass at bfb047e9, 2026-10-23 15:30 ET.
- [x] Learning → skill: mdm-engineering, Governed owner installation — separate PR #1153 documents exact numbers, normal installation, pending recovery and inherited grants; 79 local checks and all nine CI checks pass at 51582ecd, 2026-10-23 15:30 ET.

## Acceptance evidence

Normal migration commands install and upgrade both real engines with restricted runtime roles; populated state and pinned configuration survive unchanged.

## Comments

Charted from the operator’s existing implementation direction and Lavish request on 2026-10-23; no part is claimed complete by creating this ticket.


## Initial design consult

The existing registry API already provides shared policy/dataset registration
and typed reads. Its tests create their own tables, so they do not implement
normal owner migration. Reuse that API and the skill-owned prepared-effect
adapter; keep the PostgreSQL native save path intact until its replacement is
qualified. Add the missing owner installation and validation behind the existing
normal migration command. No second matching or policy algorithm.

MySQL DDL must resume under an owner lock with a checksummed pending marker,
runtime writes/execute fenced during installation, structural and grant readback,
and append-only registry protection. Configured vocabulary arrives from the
pinned catalog as data. Normal MySQL Merge Stage support remains a later ticket;
this ticket qualifies its governed storage installation and registration path.

GoF: current history (#1073, #1096, #1121, #1148) supports extending the existing
adapter seam. A new class hierarchy would not close the owner migration or
atomic-authority gaps and would increase migration/review cost.

## Implementation review — 2026-10-23 15:13 ET

### Standards

Dedicated Codex worktree; overlap guard passes. Historical migrations are
unchanged. Evidence uses invented fixtures and counts only. Registry tables,
grants, checksums and recovery live in the skill-owned adapter; catalog kinds
and policy contents arrive as data.

### Spec

Normal MySQL owner migration now installs the governed registry and retained
prepared-effect storage. Runtime governance writes and prepared-effect EXECUTE
remain denied. PostgreSQL keeps its existing normal save path and gains registry
structure and inherited column-write checks. Normal MySQL Merge Stage and SQL
Server integration remain later tickets. Initial regression evidence: 110
PostgreSQL and 118 MySQL adapter checks pass; independent installation and the
additional concurrent reader/migration case remain under qualification.

### GoF

The diff extends the established Adapter boundary rather than introducing a
second merge implementation or class hierarchy. New owner-installation logic
is isolated from application policy. The cost is a new versioned registry DDL
contract to retain; checksummed installation and corruption/recovery tests
make that cost explicit. No further pattern refactor is justified by the
current history or this diff.

## Local qualification

- 994 MDM tests passed; 7 CLI/skill-command tests passed.
- PostgreSQL: 110 adapter checks passed, plus one independently installed
  normal-owner case. MySQL: 118 adapter checks passed; the expanded governed
  file then passed 21 cases, including held-transaction/migration overlap;
  independently installed normal-owner case passed.
- SQL Server: 91 retained adapter checks passed; normal owner migration remains
  explicitly deferred. Protocol 4 remains unsupported there.
- Three historical fingerprint cases pass, covering protocols 1–4 on
  PostgreSQL/MySQL and 1–3 on SQL Server. Hash-seed checks pass.
- All local runs were bounded below five minutes. Two independent five-wheel
  installation runs each took approximately three minutes. Disposable test
  containers were stopped by their fixtures.

No hosted migration, source acquisition, activation or PostgreSQL routine
retirement was performed. The full normal MySQL Merge Stage remains ticket 04.

## Answer

Yes, the normal owner migration installs and retains governed configuration
on PostgreSQL and MySQL. PostgreSQL preserves its existing normal save path;
MySQL installs immutable policy/dataset registries, retained catalog and kind
authority, and prepared-effect storage with runtime execution withheld.
Configuration values and pins survive repeat and interrupted migrations;
restricted reads, exact numbers, schema/grant validation and recovery pass on
real isolated engines and independently installed bundles.

Implementation is published in #1152 and skill learning in #1153. Both code
and guidance revisions passed all nine checks. This checklist-only closeout
also requires green final-head PR checks before landing; that live status
belongs to the PR rather than another recursive CI-status commit. Named
operator merge approval remains separate. The normal portable Merge Stage,
full installed workflow and PostgreSQL routine retirement remain later tickets.
