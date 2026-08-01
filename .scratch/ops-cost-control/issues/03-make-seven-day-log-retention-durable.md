# Make Seven-Day Production Log Retention Durable

Type: task
Status: open
Blocked by: none

## Question

Which deploy-script and infrastructure declarations must change so every
`edgartools-prod` CloudWatch log group remains at the confirmed seven-day
Operational Forensics Window after future provisioning and application
deployments?

The live groups were set to seven days on 2026-08-01. Remove every conflicting
30-day declaration, add drift regression coverage, and verify all scoped groups
without modifying unrelated account log groups. CloudWatch retention-driven
deletion, not whole-stream deletion, owns expiration of older events.
