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

1. `MdmSecurities` — `mdm run --entity-type security`
2. `MdmPersons` — `mdm run --entity-type person` (no companies)
3. `MdmIsInsider` — `derive-relationships --relationship-type IS_INSIDER`
4. `MdmHolds` — `HOLDS`
5. `MdmCompanyHolds` — `COMPANY_HOLDS`
6. `MdmInstitutionalHolds` — `INSTITUTIONAL_HOLDS` (separate step, target 50k)
7. `MdmExport` — drain change log / endpoints
8. `MdmSync` — `sync-graph` for person/security/company + the four hold types
9. `MdmVerify` — `verify-graph --skip-native-app` (candidate integrity)

Does **not** re-run `mdm run --entity-type company|all`. Does **not** self-declare GO.

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
