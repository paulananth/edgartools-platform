# Fund legal-entity relationships

Classification: mandatory consumer
Status: planned
Depends on: shared foundation; accepted Fund and manager identities
Future spec: `docs/specs/mdm-enrichment/fund-relationships.md`

## Destination

Publish `IS_FUND-MANAGED_BY`, `IS_SUBFUND_OF`, and `IS_FEEDER_TO` through a Fund
consumer with exact source direction and temporal semantics. Do not reuse or
reverse the SEC Form ADV `MANAGES_FUND` relationship.

The spec must decide Fund/Adviser/Company endpoint classification, provisional
GLEIS node behavior, exception/absence handling, full candidate completeness,
and typed graph release gates.
