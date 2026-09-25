# Carry SEC countryCode into silver Company evidence

Type: task
Status: open
Blocked by: none
Blocks: Shell and nine other postcode matches in the Company proving run

## Outcome

Preserve SEC address `countryCode` beside `stateOrCountry` in the approved
silver Company address path and the normalized Company matching evidence.
Do not infer a country from a state code or rewrite existing bronze.

## Acceptance

- Verify the source-to-silver-to-MDM mapping on pinned SEC bronze records,
  including Shell (`0001306965`) and records with a missing country code.
- Rebuild the affected silver slice from approved bronze and show the ten
  waiting postcode matches are accounted for without weakening the state veto.
- Keep loader idempotency and the existing SEC capture contract intact.
