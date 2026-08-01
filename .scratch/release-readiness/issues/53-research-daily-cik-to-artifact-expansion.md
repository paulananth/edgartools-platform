# Explain the 3,082-CIK to 148,524-artifact expansion

Type: research
Status: resolved
Blocked by: 50

## Question

Exactly how did the production `daily_incremental` execution
`daily-incremental-ticket03-1785413694` expand 3,082 daily-index CIKs into
148,524 historical artifact candidates?

Resolve with direct evidence:

1. Trace the complete code/data path from the SEC daily-index rows through
   impacted-CIK filtering, submissions capture, recent/pagination filing
   staging, accession deduplication, configured-form selection, lookback
   filtering, and artifact iteration.
2. Reconcile the live counts at every observable boundary. Attribute as much
   of the 148,524 total as possible by:
   - recent versus pagination source;
   - form family;
   - filing year;
   - network-needed versus already-captured artifact;
   - selected versus rejected by each lookback/predicate.
3. Identify whether the expansion is intended historical catch-up behavior,
   an accidental consequence of reusing bootstrap logic, a checkpoint or
   idempotency failure, or a combination.
4. Determine why the ordinary daily path continued after `PoolTimeout`,
   whether the shared edgartools client was reset, and how the timeout behavior
   affected elapsed time without conflating it with candidate-count growth.
5. State the narrowest safe recurring-run contract: which exact daily-index
   accessions must flow into configured artifact processing, what historical
   work belongs in separate backfill/repair workflows, and which metrics must
   fail closed if expansion recurs.

Use repository source and git history, live read-only Step Functions/ECS/
CloudWatch evidence, official SEC index inputs, and canonical silver evidence.
Do not stop or mutate the running execution, change AWS, or implement code.

## Answer

[The completed findings](53-research-findings.md) reproduce the expansion
exactly:

```text
1,132,927 distinct submissions-main recent accessions
- 679,137 non-configured-form accessions
= 453,790 configured candidates before lookbacks

453,790
- 290,132 ownership candidates older than two years
-  15,134 Item 5.02 candidates older than two years
= 148,524 selected artifact candidates
```

The daily index retained accessions while it was staged, but the handoff to
submissions processing carried only 3,082 impacted CIKs. The shared
bootstrap/catch-up-style helper then enumerated each CIK's complete
`filings.recent` history and ordinary mode selected configured forms from that
historical union. All 148,524 selected candidates came from submissions-main
`recent`; pagination contributed zero.

This is a recurring-scope contract error, not a deduplication, checkpoint, or
pagination failure. `PoolTimeout` did not enlarge the candidate set, but it
amplified elapsed time: ordinary mode permits one attempt, so the client-reset
and retry branch is unreachable; failures are logged and processing continues
until 20 consecutive errors open a nonfatal circuit.

The safe recurring contract is to intersect configured artifact work with the
exact forced-index accession union and fail before attachment iteration if any
selected accession falls outside it. Historical submissions enumeration
belongs in explicit bootstrap, backfill, or repair workflows. Implementation
is tracked by
[ticket 52](52-bind-daily-artifacts-to-index-accessions.md).
