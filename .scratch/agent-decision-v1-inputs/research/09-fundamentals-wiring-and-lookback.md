# Fundamentals wiring and lookback years

Date: 2026-09-11
Live AWS: `edgartools-prod-load-history`, `edgartools-prod-daily-incremental`
(`describe-state-machine`, us-east-1, account `690839588395`).
Live Snowflake: `snow sql --connection edgartools-prod` (fiscal-year range).

Ticket: [Confirm fundamentals wiring and lookback years](../issues/09-fundamentals-wiring-and-lookback-years.md)

## Wiring

| Pipeline | entity-facts | per-filing | thirteenf | What *is* wired |
| --- | --- | --- | --- | --- |
| Live `edgartools-prod-load-history` | **yes** `FetchEntityFacts` | **yes** `FetchPerFilingFundamentals` | **yes** `FetchThirteenFHoldings` | Stage 1B after `IngestBronzeAndSilver`, `MaxConcurrency: 1`, `ToleratedFailurePercentage: 15`, large profile |
| In-repo `write_load_history_definition` | same | same | same | `deploy-aws-application.sh` ~3603–3726, 3974–3976 |
| Live `edgartools-prod-daily-incremental` | **no** | **no** | **no** | `CaptureAndVerifyNewFilings` runs `daily-incremental`; only `bootstrap-fundamentals --mode company-identity` (Stage 0 identity, not XBRL) |
| In-repo `write_warehouse_mdm_gold_definition` | no | no | no | Adding those states is still-open [Step Functions wiring for the three fundamentals modes](../../fundamentals-daily-integration/issues/04-step-functions-wiring.md) |

`edgar_warehouse/application/warehouse_orchestrator.py` has **zero**
`entity-facts` / `run_bootstrap_entity_facts` calls. The daily CLI command
does not run companyfacts internally. Architecture tests pin daily Stage 0
to `company-identity` only
(`tests/architecture/test_daily_incremental_state_machine.py`); load_history
tests pin Stage 1B modes
(`tests/architecture/test_load_history_state_machine.py`).

Live load_history entity-facts command array is
`bootstrap-fundamentals --mode entity-facts --cik-offset --cik-limit --run-id`.
No `--fundamentals-lookback-years`.

## Year limit is not 5 years

**Fetch/parse default is 2 years**, not 5.

| Control | Default | Where |
| --- | --- | --- |
| `DEFAULT_FUNDAMENTALS_LOOKBACK_YEARS` | **2** | `warehouse_orchestrator.py:268` |
| `--fundamentals-lookback-years` / `WAREHOUSE_FUNDAMENTALS_LOOKBACK_YEARS` | 2 (`0` = full history) | `cli.py` `_add_fundamentals_lookback_args` |
| Per-family overrides (item-202, proxy, thirteenf, ADV) | fall back to the shared 2 | same |
| `load_history` `FilingLookbackYearsDefault` | **2** (live + script) | discovery into `sec_company_filing`; override `{"filing_lookback_years": 0}` for full history |
| `daily_incremental` filing lookback | CLI default **0** (unbounded discovery); recurring index is 7 calendar days | no SM `FilingLookbackYearsDefault` |

Those 2-year flags apply to **artifact families** (Item 2.02, proxy, 13F
holdings extract, ADV) at `_configured_parser_accessions`. Spec
[Bound the previously-unbounded fundamentals artifact families](../../fundamentals-lookback-years/spec.md)
explicitly **does not** put a year filter on companyfacts
(`sec_financial_fact` / derived / flags).

**entity-facts / As-Of Decision Features have no year lookback.**
`run_bootstrap_entity_facts` pulls the full SEC companyfacts JSON per CIK
and parses every FY/period in it. Live gold factors/facts:
`MIN(FISCAL_YEAR)=2009`, `MAX=2026`, **18** distinct years — not a 5-year
cut.

Where **5 years** actually lives (different questions):

- Agent Decision Surface *usefulness* for proxy was locked at `[W−5y, W]`,
  then later narrowed to `[W−1y, W]`
  ([Artifact usefulness timelines](../../artifact-usefulness-timelines/map.md)
  tickets 05/10). Fetch default 2y is a known, accepted, narrower trade-off
  vs that 5y/3y agent window (lookback spec user stories 12–13).
- Gold `revenue_cagr_5y` is a **computed** factor from FY rows already in
  derived (`financial_factors.sql`). It needs five years of FY *inputs* in
  the row, not a 5-year fetch gate.

## Implication for the 21-CIK gap

Load_history **is** the integrated full-universe entity-facts path, with no
5-year cap. Daily incremental **does not** refresh companyfacts. Coverage
stays at the Ticket 42 sample until Stage 1B publish succeeds (Ticket 07 /
ecs-cost-sizing Ticket 20), not until someone sets lookback to 5.
