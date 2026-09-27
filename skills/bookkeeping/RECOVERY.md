# Recovery decisions

Read bounded status and leases first. See the
[specification](../../docs/specs/configured-bookkeeping.md) for authority and
storage semantics; use live CLI help when an option differs.

| Observation | Action |
| --- | --- |
| Waiting unit, another owner has an unexpired lease | Let bounded contention retry leave work waiting. Independent scopes can continue. Resume after ownership is available; preserve the current owner's lease. |
| Worker stopped or acknowledgement was lost | Resume the same run. Destination reconciliation precedes execution; retained receipts and business idempotency keys prevent duplicate effects. |
| Expected count exceeds verified count | Inspect pending/waiting units and prerequisite steps. Item listings are bounded; state counts cover the run. Checkpoints cannot advance over holes. |
| All work verified, deliveries pending | Restore ledger availability and resume. Delivery retries the exact event id/envelope. Completion waits for acknowledgement. |
| Publication verification failed | Correct availability/read-back failures, then resume. Exact required consumers must verify. Hosted export/graph adapters are currently unsupported. |
| Missing/corrupt manifest, receipt or output | Preserve failure evidence. When repair is authorized, recover exact original bytes from trusted retained evidence. A replacement scope/hash requires a new run. |
| Processing version changed | Use the compatible original version for that run, or submit new work. Resume cannot replace processing versions. |
| Rules retired or authoring YAML changed | Resume from the frozen export. Recover its exact bytes if missing; the live active version cannot replace it. |
| Unknown/legacy run id | Use bounded fresh run discovery. Legacy history is not imported; submit new work when no fresh run exists. |
| Compacted run | Retain its summary, references and checkpoints as audit evidence. Compacted runs cannot resume. |

Pass lease proof separately from business payloads. Database time, fencing
tokens and destination transaction guards determine mutation authority.
Completion and journal intent commit together in Bookkeeping; destination
transactions and ledger delivery are separate commits, not a transaction
across databases.

Preserve state, receipts, tokens and expiry rather than setting them with SQL
to turn a run green. Restore the failed dependency and let the engine verify.
Distinguish authorized dependency repairs from unsupported configuration or
capabilities; report the latter as implementation work with the run incomplete.
