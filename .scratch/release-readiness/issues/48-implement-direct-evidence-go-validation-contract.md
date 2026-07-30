# Implement the Direct-Evidence GO Validation Contract

Type: task
Status: open
Blocked by: 08

## Question

How must Release Evidence Automation implement ticket 08's complete packet
predicate without collecting live evidence or manufacturing human approval?

## Required work

Extend the existing pure release-evidence module, CLI, schema, and tests to:

- preserve append-only Evidence Attempts under one immutable candidate and
  select exactly one active attempt;
- enforce the exact eight-gate inventory, ordering, and required-role matrix;
- validate one indexed gate record per attempt while allowing multiple
  digest-bound artifacts and required attestations;
- reference standing rollback proof by exact mechanism identity outside the
  attempt watermark and Live-Evidence Window;
- bind the candidate at identity freeze to an external, version-controlled
  Release Authority Registry digest and validate signer handles/key
  fingerprints against it;
- enforce the seal-anchored 24-hour window and the full freeze, capture, gate
  attestation, owner attestation, and seal chronology;
- distinguish `not_ready`, `ready_for_owner`, and `go_verified`, keeping human
  NO-GO and supersession as separate terminal dispositions;
- reject unknown gates and keep addenda non-authoritative;
- verify an authorized signed annotated Release Seal against the exact
  finalized evidence commit; and
- replace `go_validation_not_implemented` only when every predicate above has
  focused and adversarial test coverage.

Keep live AWS, Snowflake, MDM, graph, dashboard, and wall-clock collection out
of the pure module. Automation may validate supplied attestations, registry
data, Git metadata, and signatures, but must not write an attestation,
disposition, or Release Seal.

## Done when

Focused tests prove every valid state transition and fail closed on missing,
duplicate, stale, superseded, unauthorized, reordered, tampered, or incorrectly
sealed evidence. Architecture tests continue to prove that no module or CLI
path can manufacture a human approval.
