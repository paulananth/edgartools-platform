# Operate scheduled connectivity and drift checks

Status: open
Owner: Claude (operator, 2026-11-17: "take over Unresolved integration and safety gaps remain documented in docs/handoff-connectivity-claude.md"; the handoff's findings are the parts below).
Type: task

## Question

Define and implement the local and production-safe operating workflow for rerunning manifest generation, AutoOntology ingestion, OpenMetadata publication, and parity verification after `Verify Snowflake, OpenMetadata, and AutoOntology parity` completes.

Acceptance criteria:

- Local verification is documented and runnable without production credentials.
- Production execution names the exact target, role, scope, and approval gate.
- Credentials stay in approved secret stores and are never emitted in logs or process arguments.
- Failures are bounded, observable, and do not partially publish uncontrolled metadata.
- Drift ownership, cadence, rollback, and stale-manifest handling are explicit.

Blocked by: 04

## Checklist

- [x] Moved unchanged to `skills/data-platform/scripts/exposure/exposure_operations.py`; the runbook to `skills/data-platform/scripts/exposure/README.md` (2026-11-17 19:59 ET)
- [ ] Approval and cadence enforced as gates, not unused labels
- [ ] A callback returning `ok: false` fails the run (today it can still produce a success receipt)
- [ ] Parity before side effects, or compensation on failure; deadlines on callbacks
- [ ] Exceptions never carry secrets through chained causes; a drift failure keeps its kind, owner and remediation
- [ ] Freshness from the manifest's own binding, not a caller-supplied creation time; naive and future dates refused; replay versus freshness stated for a rollback
- [ ] A runnable local workflow on invented tables, not a snippet with undefined inputs
- [ ] Tests that inject a secret to prove redaction, cover future dates and callback exceptions, and do not pin internal order
- [ ] Every consumer checks staleness: it calls `validate_manifest` with the exposure list and the rules root, so a manifest whose list or requirement changed is refused (today the consumers check shape and digest only); the 24-hour age check reads a creation time no manifest carries
- [ ] Nothing outside its tests calls these scripts: the runnable workflow is their first caller
- [ ] ~~The production target, role and warehouse~~ deferred to the mirror's qualification
- [ ] Learning → skill
