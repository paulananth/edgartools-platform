# Inventory source files and pipeline routing

Type: research
Status: resolved
Blocked by: 05

## Question

Which authoritative source publication and file families feed each new GLEIF
MDM Enrichment pipeline, and how must each file move through shared evidence
capture, normalization, a domain-owned consumer, checkpointing, and downstream
publication or Deferred Domain Evidence?

The answer must distinguish complete Golden Copy files, delta files, relationship
and exception files, and identifier-mapping files. It must name cadence,
completeness and recovery boundaries, source authority, intended MDM domain, and
the files that a pipeline must not consume. It is a planning inventory only and
does not authorize implementation or production publication.

## Answer

Resolved by the
[MDM Enrichment source-file pipeline catalog](../source-file-pipeline-catalog.md).

The shared GLEIF operating path has three Golden Copy families: Level 1
LEI-CDF, Level 2 RR-CDF, and Level 2 Reporting Exceptions. The daily path uses
the three 24-hour `LastDay` families. Recovery may use the three `LastWeek` or
31-day `LastMonth` families only with proven continuity; otherwise it uses the
three complete Golden Copy families. Each family retains an independent
checkpoint, and each consumer declares which verified families it requires.

ISIN, BIC, MIC, OpenCorporates, QCC, and GEM are separate ZIP-plus-CSV full
snapshot publications at their native cadences. They are not Golden Copy delta
members. S&P CIQ has no approved public bulk GLEIF file and remains a
Conditional Enrichment Source. The catalog maps every accepted file family to
its domain consumer and identifies the weekly candidate backstop as a no-new-
source-file pipeline.

Official-source verification also exposed the next design decision: XML is the
normative lossless CDF form, while the current repository fixture is JSON and
CSV can lose repeated or extension data. The production representation and
linked-family completeness boundary are therefore deferred to
[Select the Golden Copy representation and completeness boundary](07-select-golden-copy-representation-and-completeness.md).
