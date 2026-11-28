# AWS daily and month-to-date costs

Use the active account in [SKILL.md](SKILL.md). Verify it before querying:

```bash
aws sts get-caller-identity --query Account --output text
```

## Choose the billing window

Cost Explorer date boundaries are UTC, with an inclusive start and exclusive
end. Report the observation time in ET. An AWS billing day starts at 7 PM ET
the preceding evening during standard time and 8 PM during daylight time;
convert the actual boundaries using `America/New_York` when reporting them.

For month-to-date, use the first day of the current UTC billing month through
tomorrow's UTC date. This includes the open billing day, even after the UTC
date has advanced ahead of the ET date. Derive the dates from the clock:

```bash
read -r aws_cost_start aws_cost_end < <(
  uv run --no-project python -c 'from datetime import datetime, timedelta, timezone; today = datetime.now(timezone.utc).date(); print(today.replace(day=1).isoformat(), (today + timedelta(days=1)).isoformat())'
)
```

For a requested daily billing date, set `aws_cost_start` to that date and
`aws_cost_end` to the following date; use `DAILY` granularity in both queries
below. When the operator asks for "today", use the ET calendar date as the
requested date and explicitly label the result as that AWS billing day. A daily
UTC bucket is not an exact midnight-to-now ET total. If that distinction matters,
report the limitation rather than claim an exact local-day cost.

## Query the total and service breakdown

For month-to-date:

```bash
aws ce get-cost-and-usage --region us-east-1 --time-period "Start=$aws_cost_start,End=$aws_cost_end" --granularity MONTHLY --metrics UnblendedCost --output json
aws ce get-cost-and-usage --region us-east-1 --time-period "Start=$aws_cost_start,End=$aws_cost_end" --granularity MONTHLY --metrics UnblendedCost --group-by Type=DIMENSION,Key=SERVICE --output json
```

Read the total from `ResultsByTime[].Total.UnblendedCost` in the ungrouped
response. In the grouped response, `Total` can be empty: service amounts are
under `Groups[].Metrics.UnblendedCost`. Sum them with decimal arithmetic and
reconcile to the ungrouped total before rounding. Check `Unit` and each
interval's `Estimated` flag. Keep pagination enabled and include all returned
intervals and pages. The region selects the Cost Explorer API endpoint, not a
regional cost filter: these queries cover the authenticated account's visible
billing scope. A management/payer account can include linked accounts; filter
`LINKED_ACCOUNT` to the intended account when needed and apply that filter to
both queries.

## Report

- Give the month or billing date, total in the returned currency, and check time
  in ET. State the account and window if scope could be ambiguous.
- Show nonzero services, including the `Tax` row. Say whether the total includes
  tax; it includes any tax returned by these unfiltered queries. Credits and
  refunds can be negative and belong in reconciliation.
- Round only for display. Independently rounded service rows may differ from
  the rounded total by a cent; the total comes from the unrounded amounts.
- Describe `UnblendedCost` as reported charges, not a forecast or an amortized
  commitment cost. Recent charges can arrive late, and estimated totals are
  provisional. An empty result or reported zero does not prove no usage.
- Keep dated dollar amounts in the response or an operational record. The skill
  stores the procedure, so each request gets a fresh billing read.
