# Daily Company source portfolio

Date: 2026-09-12

## Recommendation

The Company MDM should process three source surfaces daily. Two already belong
to the SEC workflow; the third is the accepted GLEIF enrichment delta.

| Daily surface | Authority | Daily work |
| --- | --- | --- |
| New SEC filing inventory | SEC | Force the bounded daily-index lookback, capture required filings, discover new CIKs, process impacted CIK submissions, and apply filing-driven Company/financial changes |
| SEC ticker/exchange reference | SEC | Capture one small official snapshot and apply changed listing identifiers/universe membership with source history |
| GLEIF legal-entity evidence | GLEIF | Capture one 24-hour Level 1, relationship, and reporting-exception delta; apply only changed accepted links and generate candidates for newly eligible or materially changed entities |

There is no evidence for another full-universe Company feed that needs daily
loading. Specifically:

- Do not poll all SEC companyfacts daily. Refresh facts for CIKs affected by
  new filings and use the existing reconciliation/backstop behavior.
- Do not rematch the full MDM universe to GLEIF daily. Run the unresolved and
  unmatched candidate backstop weekly and full reconciliation monthly.
- Do not put ISIN-to-LEI into Company enrichment. It is the one additional
  official daily mapping, but its semantics are Security -> issuer legal
  entity; it needs a separate Security consumer.
- Do not force OpenCorporates, BIC, MIC, QCC, or GEM into a daily schedule.
  Their native publications are bi-weekly or monthly. S&P CIQ is weekly and
  bulk access may require a subscription.
- Do not treat market prices, quotes, or daily market capitalization as Company
  identity. If later acquired, they belong to a dated Market/Security fact
  domain.
- Do not introduce sanctions, credit, ESG, or commercial company feeds through
  this GLEIF specification. They have distinct authority, licensing, matching,
  and freshness contracts and require separate decisions.

## Why the existing SEC path is sufficient

The current `daily-incremental` implementation force-refreshes a bounded SEC
daily-index window, collects impacted CIKs and Form 15 deregistration evidence,
enrolls newly observed CIKs, captures their submissions and required filings,
and runs MDM/gold processing. This is already the correct event trigger for SEC
company identity and filing-derived facts. A separate daily full-company sweep
would duplicate source requests without a new authority signal.

The SEC ticker/exchange snapshot is small and independently useful for ticker
changes and the accepted company-eligibility boundary. It should be captured
once per daily Company run, not used as a substitute for filings, CIK, or
historical listing evidence.

## Failure and replay boundary

Each daily surface keeps an independent checkpoint and can be replayed by its
source date/publication. A missing GLEIF day does not block SEC filing capture,
and an SEC failure does not authorize advancing the GLEIF checkpoint. The MDM
publication watermark advances only for evidence whose source capture and
application completed. Monthly reconciliation proves GLEIF completeness; the
existing SEC recurring lookback/backstop proves filing-inventory completeness.

## Evidence

- Repository `edgar_warehouse/application/warehouse_orchestrator.py` implements
  the forced daily-index lookback, impacted-CIK enrollment, Form 15 demotion,
  submissions capture, and filing-driven processing.
- Repository `infra/scripts/deploy-aws-application.sh` defines the recurring
  daily execution and MDM/gold handoff.
- [GLEIF Golden Copy and Delta Files manual](https://www.gleif.org/lei-data/gleif-golden-copy/2022-02-23_gleif-golden-copy-and-delta-files_v2.2-final.pdf)
  defines the 24-hour delta for Level 1, relationship, and exception families.
- [GLEIF mapping catalog](https://www.gleif.org/en/lei-data/lei-mapping)
  defines each mapping's native cadence.
