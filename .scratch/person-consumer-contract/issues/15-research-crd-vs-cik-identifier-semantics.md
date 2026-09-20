# Research CRD versus CIK: what each identifies, and whether they can be merged into one Person key

Type: research
Status: open
Blocked by: none

## Question

Ticket 02 Q2 asked whether a CRD number can bind a Person. The operator
wants full understanding first: what is the difference between an SEC CIK
(as it appears on Form 3/4/5 as `owner_cik`) and a FINRA/IAPD CRD number
(as it appears on Form ADV), and if a natural person can hold both, do
they need to be merged into one unique identifier — or kept as two
identifiers on one identity?

Answer from primary sources, cited:

1. **Issuer and scope of each identifier.** Who assigns a CIK and to what
   (SEC EDGAR filer accounts: companies, funds, *and* individuals who file
   Forms 3/4/5, 13D/G, etc.). Who assigns a CRD number and to what (FINRA
   Central Registration Depository: broker-dealer firms, investment
   adviser firms, and *individual* registered representatives / investment
   adviser representatives). Can one natural person hold a CIK, a CRD, both,
   or neither? Is either ever reassigned or retired?
2. **Firm vs individual on Form ADV.** Which Form ADV / IAPD fields say
   whether a registrant is an individual (e.g. Item 3 organization form
   "sole proprietorship", the IAPD "individual" record type, Schedule A/B
   owner rows with an "individual" flag and their own CRD numbers). Does
   the SEC IAPD bulk archive the platform ingests carry those fields?
   Verify against the repo: `edgar_warehouse/parsers/adv.py`,
   `edgar_warehouse/mdm/adv_bulk.py`, `edgar_warehouse/application/`
   (the `fetch-adv-bulk` command and the archive URL/columns it reads).
3. **Cross-references between the two systems.** Does any SEC or FINRA
   source publish a CIK↔CRD crosswalk for individuals? Does Form ADV
   itself carry the adviser's SEC file number and CIK (Item 1)? Do
   Forms 3/4/5 ever carry a CRD? Is name+context the only join otherwise?
4. **Uniqueness semantics.** Is CIK one-per-person in practice, or can an
   individual hold more than one (e.g. filing errors, trusts in the
   person's name)? Is CRD one-per-person across firms (an individual
   keeps the same CRD when moving firms)?
5. **Implication for a Person key.** Given the above, state the options
   factually (one merged surrogate; two typed identifiers on one identity
   with a uniqueness invariant per type; CRD as an Adviser-profile
   attribute only) and what each requires of the data the platform
   actually has. No recommendation — ticket 02 decides.

Write to `research/15-crd-vs-cik-identifier-semantics.md`, same shape as
research 11–14: sources read (URLs for external, `path:line` for repo),
numbered findings, "what this settles for ticket 02 Q2", "could not be
determined". External sources: SEC EDGAR filer-manual / CIK definitions,
SEC IAPD data download documentation, FINRA CRD/BrokerCheck definitions,
Form ADV instructions and glossary. Primary sources only, no secondary
summaries.
