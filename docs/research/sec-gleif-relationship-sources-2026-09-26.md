# SEC and GLEIF inputs, and the relationships each can support

Date: 2026-09-26. Sources: the accepted Clean MDM domain model, the source-evidence catalog, the GLEIF open-data note of 2026-09-11, and the Form 3/4/5 and GLEIF Level 1 prototype contracts. No new download was made.

## SEC input files

| Input | File | Relationship it can support | What it cannot do |
| --- | --- | --- | --- |
| Company submissions | `submissions.zip` / `submissions.json` per CIK | None. It identifies the Company. | It does not link a parent, a holder, or a security. |
| Forms 3, 4, and 5 | Ownership XML inside the filing `.txt` | `EMPLOYED_BY` from the reporting owner to the issuer, with the role flags. Holdings from that Person or Company to a security named by title. | No CUSIP. The title does not mint a Security when the issuer already has more than one class. |
| 13F-HR | Information-table XML (`infotable.xml` and the same file under other names) | The Security, from the CUSIP. Holdings from the filing manager to that Security. Issuer name is evidence for `ISSUED_BY` after the Company or Fund Company is mastered. | The issuer string does not create the Company. It does not make the manager the beneficial owner. |
| Form ADV bulk | IAPD CSV inside the monthly ZIP | Adviser Profile on a Company or Person. `MANAGES_FUND` from that adviser to a private fund. | It is not `IS_ENTITY_OF` or `IS_PERSON_OF`. The profile shares the holder's identity. |
| N-CEN | Annual census of a registered fund | Fund Company and Fund Series. `MANAGES_FUND` from the named investment adviser to the series. | The adviser is not the issuer of the ETF share. |
| N-PORT | Portfolio holdings | Holdings from the Fund Series to Securities identified by CUSIP. | Not an issue link. |
| N-MFP | Money-market portfolio | Same holding shape, with CUSIP and ISIN. | Not an issue link. |
| Schedules 13D and 13G | Beneficial-ownership filing | A holder and a class CUSIP. Another filing of a Security that already exists. | Not a GLEIF accounting parent. |
| N-PX | Proxy votes | Confirms a CUSIP. | Not a holding quantity. |
| DEF 14A | Proxy HTML | `EMPLOYED_BY` from a named person to the Company. | Not a config-parsed source. The compensation table stays a hand-written parser. |
| 10-K auditor fact | XBRL `dei` auditor | `AUDITED_BY` for one engagement. | Not a permanent auditor field. |
| Exhibit 21 | Subsidiary list | Evidence for an ownership parent. | Not yet a reliable parent edge. |
| Form 144 | Notice | A security title only. | No CUSIP, so it does not create a Security. |

The only SEC contracts implemented as config today are Forms 3/4/5 (`sec.ownership`) and the 13F information table. ADV, N-CEN, and N-PORT are parsed by edgartools or not at all. They are not Source Contracts yet.

## GLEIF input files

| Input | File | Relationship it can support | What it cannot do |
| --- | --- | --- | --- |
| Level 1 LEI-CDF 3.1 | Golden Copy XML, JSON, or CSV | None by itself. It identifies the legal entity, its names, legal form, category, and status. Category decides Company, Fund, Branch, Government Entity, or International Organization. | A previous name is an alias, not a second Company. |
| Level 2 RR-CDF 2.1 | Relationship records in the same Golden Copy family | Direct accounting parent. Ultimate accounting parent. `IS_INTERNATIONAL_BRANCH_OF`. `IS_FUND-MANAGED_BY`. `IS_SUBFUND_OF`. `IS_FEEDER_TO`. | These parents are accounting consolidation. They are not SEC equity ownership, beneficial ownership, or control. |
| Reporting exceptions 2.1 | REPEX file in the same family | No edge. It records why a direct or ultimate parent was not published. | A missing parent is not proof of no parent. |
| ISIN to LEI | Mapping snapshot | Evidence that a security identifier's issuer is an accepted LEI. | Absence does not retire a Security. |
| MIC to LEI | Mapping snapshot | Venue operator. The MIC is not a Company identifier. | Not ownership. |
| BIC to LEI | Mapping snapshot | An organization or Branch identifier. | Not a parent. |
| OpenCorporates, QCC, GEM to LEI | Mapping snapshots | Corroborating identifiers. | Not merge authority, and not asset ownership. |

The prototype GLEIF contract reads Level 1 company fields only. It does not read RR-CDF, so it does not emit the six relationship types.

## Same fact, two sources

| Master relationship | SEC source | GLEIF source |
| --- | --- | --- |
| Company identity | CIK on submissions | LEI on Level 1. Joined only by the Company match, not by name. |
| Accounting parent | Not an SEC product in this set | RR direct and ultimate accounting parent |
| Ownership parent | Exhibit 21, and 13D/13G as beneficial ownership | Not GLEIF. GLEIF refuses this meaning. |
| `MANAGES_FUND` | ADV and N-CEN | `IS_FUND-MANAGED_BY`. Kept as GLEIF's own edge. It does not replace the ADV edge. |
| Fund structure | N-CEN series | `IS_SUBFUND_OF`, `IS_FEEDER_TO` |
| Branch | Not in the SEC set above | `IS_INTERNATIONAL_BRANCH_OF` |
| `ISSUED_BY` | 13F issuer name, after the Company or Fund Company exists. ISIN-LEI can corroborate. | ISIN to LEI |
| Holdings | 13F, Forms 3/4/5, N-PORT, N-MFP | None |
| `EMPLOYED_BY` | Forms 3/4/5 and DEF 14A | None |
| `AUDITED_BY` | 10-K auditor | None |
