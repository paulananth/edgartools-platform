# Research what ADV Schedule A/B `OwnerID` is, and whether it can be a deterministic Person identifier

Type: research
Status: open
Blocked by: none

## Question

Research 15 found `IA_Schedule_A_B` in the `ADV_Filing_Data_*.zip` the
platform already downloads: 16,139 rows, 11,126 flagged `I` (individual),
each with `Full Legal Name`, `Title or Status`, `Ownership Code`,
`Control Person`, and an `OwnerID` column whose definition SEC does not
publish. A 4-row probe matched 2 by number and name against IAPD's
individual id. Ticket 02 Q2 hinges on whether `OwnerID` is the person's
own CRD number (then it binds deterministically, like `owner_cik`) or
something else (then Schedule A/B rows are name-only).

Establish, from primary sources and a real sample:

1. **Documentation.** Does any SEC/IARD/FINRA document define `OwnerID`
   (the IARD technical/data specification, the FOIA "ADV Filing Data"
   README or data dictionary inside the ZIP, Form ADV Schedule A
   instructions' "CRD No." column)? Quote it or record that none exists.
2. **Empirical test, sized to convince.** Take a stratified sample of at
   least 200 `I` rows (spread across filings, titles, and `OwnerID`
   magnitude), and for each, query IAPD's individual lookup by `OwnerID`
   (`https://adviserinfo.sec.gov/individual/summary/<id>` or the JSON
   search API research 15 used). Record: id resolves (yes/no), name match
   (exact normalized / partial / none), and whether the resolved
   individual's firm history includes the filing firm's CRD. Also test
   whether `OwnerID` values ever collide across *different* names in the
   archive, and whether the same name+firm has a stable `OwnerID` across
   monthly archives (fetch one earlier month and compare).
3. **Non-individual rows.** For `DE`/`FE` rows, what is `OwnerID` — a
   firm CRD, an IARD org id, or blank? Test 20 against IAPD's firm lookup.
4. **Coverage.** What fraction of the 11,126 individual rows have a
   non-null `OwnerID`? Are there `I` rows with an `OwnerID` that resolves
   to a *firm* or vice versa?
5. **Conclusion, factual.** State whether the evidence supports
   "`OwnerID` is the individual's CRD number, unique per natural person"
   at a standard comparable to the repo's other identifier decisions, or
   what it falls short of. No recommendation — ticket 02 decides.

Rate-limit and identify politely against IAPD (this is a public site,
not an API contract): one request per second, a descriptive User-Agent
with the operator's contact email as SEC's fair-access policy asks, stop
at the first HTTP 403/429. Record the exact query, timestamps, and a
SHA-256 of the sample and results next to research 15. Write to
`research/16-schedule-ab-ownerid-meaning.md` in the same shape.
