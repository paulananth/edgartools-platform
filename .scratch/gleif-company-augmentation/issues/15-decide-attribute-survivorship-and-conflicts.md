# Decide GLEIF attribute survivorship and conflict handling

Type: grilling
Status: resolved
Blocked by: 03

## Question

Which GLEIF attributes remain source-grained evidence, which may become MDM
projections, and how are disagreement, temporal change, source retirement, and
downstream publication handled without overwriting SEC authority?

## Recommendation

Preserve every GLEIF field at source grain. Project only explicitly selected
legal-entity attributes with separate source and observed/effective validity;
never overwrite SEC filing or financial facts. Quarantine identity conflicts,
retain compatible parallel evidence, and close a projection only from explicit
source change or complete reconciliation.

## Done when

Every first-slice field has an authority, comparison class, precedence or
parallel-display rule, temporal rule, conflict state, and retirement trigger.

## Answer

Preserve the complete Level 1 record at source grain. The first consumer may
project LEI/source-link status; legal form; legal jurisdiction; entity and LEI
registration status; registration dates, managing LOU, validation source;
registration-authority identity; and entity creation date. Keep legal and
headquarters addresses, names, legal events, expiration fields, and successor
LEIs as distinct source evidence initially; successor data participates in link
revalidation rather than silently replacing an LEI.

SEC and GLEIF values remain parallel when they describe different concepts.
Comparable disagreement enters field-conflict review—the five measured
jurisdiction conflicts are seeded there—and cannot overwrite SEC evidence.
Every value retains source, observed/effective validity, status, and version.
Business-close only from explicit source change or complete reconciliation;
partial-delta absence never retires a value.

Accepted by the user during the 2026-09-12 `/grill-with-docs` session.
