# Ticket 08: labelling standard for SEC-to-GLEIF links

Written 2026-09-25, before any qualification label. It is frozen when the
matching rule is frozen; a change after that needs a fresh draw.

A label answers one question: **is the SEC filer (CIK) the same legal entity
as the GLEIF record (LEI)?** The legal entity is the one legal person that
files with SEC or registered the LEI, not its group or brand.

## Evidence a label may use

- SEC bronze for the CIK: current and former names, state or country of
  incorporation, business and mailing addresses, forms filed, tickers.
- The GLEIF Level 1 record in the pinned Golden Copy (2026-09-11 16:00 UTC):
  legal and other names, legal form code, legal jurisdiction, legal and
  headquarters addresses, registration authority and its entity ID, entity
  and registration status, successor.
- No SEC or GLEIF request, and no guessed identifier. Where the evidence does
  not decide, the label is `unresolved`, and `unresolved` counts as **wrong**.

## Readings

1. **Same name, different legal form: different.** "X Inc." and "X LLC", or
   "X Corp" and "X, Inc.", are two legal persons, usually a parent and its
   subsidiary.
2. **Operating partnership and its REIT: different.** "X Properties Inc."
   and "X Properties LP" are two legal persons (an UPREIT's two issuers).
3. **Holding company and operating subsidiary: different**, even with an
   identical name in two jurisdictions (for example a bank holding company and
   its bank).
4. **A foreign issuer and its own LEI: same.** A 20-F filer and the GLEIF
   record of that same company in its home jurisdiction are one entity. Its
   US subsidiary or branch is not.
5. **GLEIF status.** LAPSED (not renewed) and RETIRED still name the entity.
   DUPLICATE and ANNULLED never make a correct link. A GLEIF entity that is
   INACTIVE, or retired into a successor by merger, while its SEC filer still
   files, is `unresolved` unless the evidence shows the SEC filer is that
   entity. A case no reading covers goes to the operator.
6. **Renamed entity: same** when the SEC former names and the jurisdiction
   show one entity under two names, for example a SPAC renamed after its
   merger.
7. **Branch: different.** A GLEIF BRANCH is not a legal entity. The rule
   never binds to one.
8. **Fund or series: different** from the Company, whatever the name.

## Who labels

Claude reads each pair by hand, as ticket 12's classification labels were
read. The labels are bronze-evidence readings, not registry adjudications.
Each wrong or unresolved pair carries a one-line note.
