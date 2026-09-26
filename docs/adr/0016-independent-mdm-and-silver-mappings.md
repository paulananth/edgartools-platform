# Shared source parsing with independent MDM and analytical mappings

Status: accepted, 2026-09-26. Q1–Q6 accepted individually; complete shared
understanding confirmed by Q7, reply verified 2026-09-26 11:11 ET.

MDM and analytical silver will consume versioned stored source records through
separate mappings, progress and retries, preserving all structured source fields
before consumer transformations. Shared reading avoids routine duplicate raw
decoding; separately versioned consumer mappings rerun only affected work, while
reader changes create new parsed versions. Keep current and needed parsed versions
under the existing source-retention constraints, and prove the boundary on SEC
Company and GLEIF before broader migration.

## Consequences

- MDM interpretation no longer depends on the analytical projection's selected
  fields or completion. Combined outputs still require compatible verified inputs.
- Shared parser failures remain shared prerequisites; stored parsed evidence adds
  storage, lineage verification and compatibility work. Savings require measurement.
- Existing acquisition, MDM transaction/journal, identity approval and raw-retention
  contracts remain in force. A source-specific separate-reader exception is allowed.
- The proposed Source Contract's silver-to-Dataset Contract coupling needs an
  explicit amendment. This record activates no consumer, rule or deployment.

See the [review package](../../.scratch/mdm-silver-boundary/architecture.md) and
[architecture requirements](../../.scratch/mdm-silver-boundary/specification.md).
