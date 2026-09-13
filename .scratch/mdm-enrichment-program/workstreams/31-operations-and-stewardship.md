# Operations and stewardship

Classification: cross-cutting operating workstream
Status: planned
Depends on: shared foundation review-state contract
Future spec: `docs/specs/mdm-enrichment/operations.md`

## Destination

Operators can see source freshness, publication identity, checkpoint continuity,
candidate and conflict queues, deferred domains, retirement events, replay
status, downstream parity, budgets, and next action without reconstructing truth
from CloudWatch logs.

Specify separate identity-link, field-conflict, relationship-endpoint, and
identifier-mapping queues; steward and rule-change approval; service objectives;
alarms; runbooks; backpressure; retry exhaustion; and evidence-bound incident
recovery.
