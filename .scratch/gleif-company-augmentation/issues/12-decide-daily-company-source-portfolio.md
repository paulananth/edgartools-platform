# Decide the daily Company source portfolio

Type: research
Status: resolved
Blocked by: 07, 08, 11

## Question

Beyond the accepted GLEIF delta, which Company facts need daily acquisition or
processing, and which should remain filing-driven or follow another source's
native cadence?

## Required evidence

- Compare the current scheduled SEC `daily-incremental` path with the proposed
  GLEIF Company enrichment path.
- Separate entity identity/lifecycle, filing facts, security mappings, market
  data, and other MDM domains.
- Do not create daily polling merely because a source can be polled daily.
- State the source authority and trigger for every recommended daily input.

## Done when

The specification has an explicit daily portfolio and an explicit list of
candidate feeds that must not be added to the Company daily job.

## Answer

Resolved by [`../research/12-daily-company-source-portfolio.md`](../research/12-daily-company-source-portfolio.md).

The Company MDM daily portfolio should contain the existing SEC new-filing and
impacted-CIK identity path, a small official SEC ticker/exchange snapshot, and
one 24-hour GLEIF Level 1/relationship/exception delta. SEC companyfacts and
filing-derived attributes remain event-driven by impacted CIKs. No additional
full-universe Company dataset needs daily loading. The daily ISIN-to-LEI file
belongs to a separate Security-to-issuer consumer.
