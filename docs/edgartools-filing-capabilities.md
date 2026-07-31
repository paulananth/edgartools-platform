# EdgarTools filing capabilities

## Repository boundary

This platform uses edgartools for filing discovery, attachment metadata, and
structured parsing. It does not use edgartools high-level content accessors as
the source of immutable bronze bytes. Each selected filing document and
attachment is instead downloaded from its canonical SEC archival URL through
the repository-owned byte-preserving HTTP client.

## Useful edgartools data

- Filing lookup by accession and filing metadata such as form, dates, issuer,
  and primary document.
- Attachment inventory: sequence number, document name, document type,
  description, canonical URL, and primary-document membership. This includes
  multi-attachment filings such as 13F information tables and earnings 8-K
  exhibits.
- Structured parser surfaces after bronze capture, including ownership Forms
  3/4/5 via `edgar.ownership.Ownership.from_xml`, financial statements/XBRL,
  exhibits, and filing text/table views where appropriate.

## Content rule

`attachment.content` and other high-level edgartools content values may be
decoded, normalized, or otherwise library-transformed. They are suitable for
transient parsing only after a caller accepts that contract; they are not
evidence of the raw SEC artifact and must not be persisted as bronze.
