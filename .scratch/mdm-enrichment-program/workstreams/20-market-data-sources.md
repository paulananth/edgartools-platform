# Market-data sources

Classification: conditional source family
Status: research required
Depends on: Security and Market/Venue domain contracts
Future spec: `docs/specs/mdm-enrichment/conditional/market-data.md`

Evaluate dated prices, quotes, corporate actions, and market capitalization as
Security/Market facts, never Company identity. Decide `adopt`, trigger-bound
`defer`, or `reject` per provider after authority, license, coverage, adjustment
methodology, cadence, cost, replay, retention, and point-in-time correctness are
proven.
