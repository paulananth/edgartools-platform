# Connect worker authority and publication recovery

Type: task
Status: open
Parent: [Complete portable MDM and retire PostgreSQL business logic](../map.md)
Blocked by: 04

## Question

Can the normal worker preserve authority through commit and recover publication safely on both engines?

## Parts

- [ ] Integrate the demonstrated destination-local fence/expiry capability with the normal worker; do not expand into unrelated Bookkeeping conversion.
- [ ] Refuse expired, superseded and same-token/different-attempt proofs through commit, including duplicate and caller-held transaction cases; test malformed direct database requests as well as Python validation.
- [ ] Preserve publication-on-input, index-only no-publication, per-consumer delivery, retry receipts and root-run observations; recover after interrupted commit/delivery.
- [ ] Freeze and verify protocol 1–3 migration fingerprints; review and qualify the minimal new protocol independently of onboarding.
- [ ] Learning → skill: update its owning skill on a separate branch/PR, or record none.

## Acceptance evidence

Normal configured worker and publication recovery pass on each real engine with restricted roles, late expiry, overtaking, rollback and zero-work replay.

## Comments

Charted from the operator’s existing implementation direction and Lavish request on 2026-10-23; no part is claimed complete by creating this ticket.
