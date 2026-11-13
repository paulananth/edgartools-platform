# Is the hosted Snowflake Postgres qualification and credential gate cleared?

Type: research
Status: resolved
Blocked by:

## Question

Is there approved evidence, newer than the checked-in `docs/specs/mdm/state-of-build.md` record that
defers Snowflake Postgres qualification, that (a) qualifies `EDGARTOOLS_PROD_MDM` as a target for
production source loads, and (b) shows the MDM application and admin credentials were rotated
after the session in which they were exposed?

Search only local, non-credential sources: the repository's checked-in specs and plans, the private
`~/.local/share/edgartools/hosted-prod/` governance and worker metadata (names and timestamps only —
never read `create-instance.json` raw, never print any connection string or credential value), the
private load-log directory, and any newer approved qualification record in the repo.

Report, with the evidence path and date for each claim:

1. Whether hosted qualification is cleared, still deferred, or contradicted by a newer record.
2. Whether credential-rotation evidence exists and where it lives.
3. Whether the current private environment files point at a rotated credential set or at the
   exposed one — by timestamp and file identity only, never by value.
4. The consequence for the measurement: may a new production source load be submitted, or is the
   measurement retrospective-only?

Write the findings to `.scratch/measure-prod-mdm-loads/evidence/01-hosted-qualification-and-credential-gate.md`
with no credentials, DSNs, host values or record identifiers. Link the file from this ticket's
answer.

## Answer

Evidence: [01-hosted-qualification-and-credential-gate.md](../evidence/01-hosted-qualification-and-credential-gate.md)
(branch `codex/wayfinder-measure-prod-loads-20261113`, commit `7758ed5b`).

- **Hosted qualification: uncleared.** `docs/specs/mdm/acceptance.md:5,120-121` and
  `docs/specs/mdm/state-of-build.md:133-136` both defer Snowflake Postgres qualification, and no
  newer approved record exists in the checkout. The instance is READY, which is not qualification.
- **Credential rotation: not evidenced.** The only `RESET ACCESS` hit is a read-only query-history
  *search*, not a credential change; `create-instance.err` is empty.
- **The live env files still carry the unrotated credentials.** Fingerprints (value hashes only)
  show every credential-bearing value in `governance.env` is byte-identical to
  `governance.env.before-reset-20261112`; only non-credential keys were added on 2026-11-12.
- **Consequence: the measurement is retrospective-only.** No new production source load may be
  submitted, and no MDM/Postgres connection may be made with these credentials.
