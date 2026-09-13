# Lock the shared GLEIF Evidence Capture boundary

Type: grilling
Status: resolved
Blocked by: 06

## Question

Should one shared GLEIF source path capture all Level 1 entities, Level 2
relationships, and reporting exceptions while each MDM domain consumes only
the records that belong to it?

## Answer

Yes. The user accepted GLEIF Evidence Capture as the source-wide boundary. It
retains the complete official publication rather than filtering acquisition to
SEC companies. Company, Fund, Security, Branch, and later entity-domain
consumers must route records by explicit GLEIF category, relationship type, and
identifier semantics. A record is not inserted into Company MDM merely because
it has an LEI.

The current specification still delivers Company Legal-Entity Enrichment as
the first consumer. Separate map tickets decide GLEIF relationship-type and
identifier-mapping routing before the shared capture specification closes.
