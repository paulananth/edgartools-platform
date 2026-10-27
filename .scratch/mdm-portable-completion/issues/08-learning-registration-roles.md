# Qualify configuration registration and verifier duties

Type: task
Status: claimed
Parent: [Retire PostgreSQL business routines and caller paths](08-retire-postgresql-business-routines.md)
Blocked by: none for reusable guidance; implementation is PR #1190

## Parts

- [x] Add source-neutral qualification guidance for separate owner, registrar, worker and verifier duties — 2026-10-26 21:14 ET: added to the governed owner installation reference.
- [x] Verify the guidance against the demonstrated local bootstrap failure and retained restricted-role tests — 2026-10-26 21:14 ET: implementation PR #1190 retains successful registration and rights/rollback/drift checks; guidance requires each actual role path.
- [ ] Pass genericity checks, three-axis review and overlap guard; publish a separate skill PR.
- [x] Learning → skill: 2026-10-26 21:14 ET: `mdm-engineering/references/storage-adapters.md`, “Governed owner installation”: owner-only registration does not qualify separate registrar/worker/verifier duties.

## Evidence

The real separate-role bootstrap in ticket 08 could register historical
configuration but lacked governed metadata access. An owner-only registration
proof did not expose this missing duty. The implementation's PostgreSQL checks
prove allowed registration, denied master/gate writes, denied runtime
registration, rollback and privileged-function drift. Other engine role paths
must be reported at their own qualified scope.

## Review

### Standards

Separate fresh branch and worktree, source-neutral shared guidance. The exact
changed reference passes the genericity check. No runtime or migration is changed.

### Spec

Captures ticket 08's demonstrated permissions gap as a reusable qualification
criterion. Each engine retains its own role-path gate; no unsupported delegated
registration is presented as supported.

### GoF

Keep the existing owner/store/adapter boundary. This lesson changes the proof
required at that boundary and introduces no new class or parallel policy logic.
