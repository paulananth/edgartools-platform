# Residual holds graph pipeline (Ticket 20 handoff residual)

## Why this exists

Ticket 20 strict bulk-load completion evidence (2026-07-25) left a **reported
non-blocking residual** on the activated graph generation:

| Gap | Status on Ticket 20 generation |
| --- | --- |
| `IS_INSIDER` edges | empty |
| security nodes | empty |
| `HOLDS` / related ownership holds | empty |
| `INSTITUTIONAL_HOLDS` | empty |

`EMPLOYED_BY` bulk-load and graph endpoint integrity were in-scope for that
PASS package. Filling holds/insider/13F graph types is a **separate residual
pipeline** so operators do not re-run the full Ticket 20 freeze map.

Ticket 21 proved **person + IS_INSIDER** for a 10-CIK sample. This pipeline
productionizes residual holds population (including 13F) for the whole
warehouse silver surface without re-resolving companies.

## Production state machine

**Name:** `edgartools-<env>-residual-holds-graph`  
**Registered by:** `infra/scripts/deploy-aws-application.sh` (`residual_holds_graph`)

### Stages

1. `MdmSecurities` — `mdm run --entity-type security` (**mdm-large** 8 GiB)
2. `MdmPersons` — `mdm run --entity-type person` (no companies; mdm-large)
3. `MdmIsInsider` — `derive-relationships --relationship-type IS_INSIDER` (mdm-large)
4. `MdmHolds` — `HOLDS` (mdm-large)
5. `MdmCompanyHolds` — `COMPANY_HOLDS` (mdm-large)
6. `MdmInstitutionalHolds` — `INSTITUTIONAL_HOLDS` (separate step, target 50k; mdm-large)
7. `MdmExport` — drain change log / endpoints (mdm-large)
8. `MdmSync` — **full** `sync-graph` (all entity/relationship types) tagged
   `--generation-id $$.Execution.Name` (mdm-large). Partial type filters are
   **forbidden**: they leave Fund/Adviser/EMPLOYED_BY off the candidate gen.
9. `MdmVerify` — `verify-graph --skip-native-app --generation-id $$.Execution.Name`
   (candidate integrity; **mdm-small**). Verifying without generation_id checks
   the **active** pointer vs full MDM and fails after residual MDM fills.

Does **not** re-run `mdm run --entity-type company|all`. Does **not** self-declare GO.
Does **not** auto-activate — operator runs `mdm graph-activate` after PASS.

### Memory / OOM note (2026-07-25)

First prod execution `residual-holds-20260725T221723Z` failed on `MdmSecurities`
with `OutOfMemoryError` / exit **137** on `edgartools-prod-mdm-medium` (**2 GiB**).
Root cause: full-universe security resolve loads silver holdings/ownership surfaces
beyond 2 GiB. Fix: register `mdm-large` (2048 CPU / **8192** MiB) and wire residual
heavy stages to it; also raise default `mdm-medium` to **4096** MiB for other MDM
workflows. **Do not redrive** the OOM execution after task-def/SM change — stop it
and start a **new** execution name against the updated state machine.

### Start (prod example)

```bash
aws stepfunctions start-execution \
  --region us-east-1 \
  --profile sec_platform_deployer \
  --state-machine-arn arn:aws:states:us-east-1:690839588395:stateMachine:edgartools-prod-residual-holds-graph \
  --name "residual-holds-$(date -u +%Y%m%dT%H%M%SZ)" \
  --input '{"trigger":"operator","pipeline":"residual_holds_graph","note":"Ticket20 handoff residual"}'
```

After a successful candidate sync, activation remains an **explicit operator**
step (`mdm graph-activate`) if a new generation should become active.

## Local operator path

```bash
./scripts/ops/sync-relationships.sh --residual-holds
# equivalent scoped types + security/person resolve, no company re-load
```

## Related

- Handoff residual: `.planning/.continue-here.md`, `docs/release-readiness/ticket20-completion-2026-07-25.md`
- Ticket 21 person/IS_INSIDER sample: `docs/release-readiness/ticket21-insider-coverage-10cik-2026-07-25.md`
