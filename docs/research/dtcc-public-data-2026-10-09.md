# DTCC public data for MDM / SEC enrichment

Research: 2026-10-09. Official DTCC and GLEIF sources only. Research evidence, not ingestion qualification.

## Useful public sources

| Source | Verified access / coverage | Proposed use (inference) | Limits |
| --- | --- | --- | --- |
| DTC member directories | [Official directory](https://www.dtcc.com/support/dtc-directories) explicitly says participant alphabetical/numerical lists, settling banks and depository facilities are free to the public. Current page date September 30, 2026; XLSX links for participants, settling banks, pledgees, direct registration. | Add DTC participant/account identifier and membership role observations to already resolved financial companies; compare with SEC broker/institution names. | Account/member ID is not CIK or LEI. Membership alone cannot prove an identity binding or beneficial ownership. Download link fetch through web tool failed; parent reported urllib403, so schema/download not qualified. |
| Important notices RSS | [RSS documentation](https://www.dtcc.com/rss-feeds) states notices, financial statements, rule filings, newsletters and releases are public without subscription/password. Categories include DTC membership, reference data, distributions, mandatory reorganizations, redemptions, issuer services. | Event evidence, membership changes and securities servicing changes to complement SEC filings. | Notices are selective documentary evidence, not complete normalized corporate-action history. |
| DDR Public Price Dissemination | [Market data hub](https://www.dtcc.com/market-index-data) links [dashboard](https://pddata.dtcc.com/ppd/) and says search/analyze/download real-time/historical derivatives reporting. [DDR rulebook notice](https://www.dtcc.com/-/media/Files/pdf/2023/3/10/DDR40.pdf) section5.1 addresses CFTC, Canada and SEC reporting; section5.1.4 excludes party identity. | Security/derivatives activity enrichment where underlying identifiers permit a defensible instrument link. | Public transaction data cannot identify swap holders/counterparties. Not an ownership feed. Reporting contains capped/rounded notionals. Dashboard is JS-only to this tool; current export schema, endpoint stability and backfill not qualified. |
| GTR public aggregate reports | [Hub](https://www.dtcc.com/market-index-data) publishes jurisdiction links for Australia, Canada, EU/UK EMIR, FINMA, JFSA, MAS, EU/UK SFTR. | Market-level context and controls. | Aggregated data is usually weak Company identity evidence; individual report schemas not validated. |
| TIW CDS top1000 / index aggregates | Official search index for [hub](https://www.dtcc.com/market-index-data) describes quarterly top1000 reference-entity CDS aggregates and semiannual index-roll rankings. | Potential reference-entity name candidates, CDS activity/liquidity observations. | **Availability discrepancy:** cached search result includes this section but live page open does not. No current download verified. Do not list as a qualified accessible feed until current link/file is verified. Name-only references cannot auto-bind. |

## Paid or restricted products, not public bulk datasets

- [Security Master File Data](https://www.dtcc.com/reg-sci/sitecore/content/dtcc/Home/data-services/corporate-actions-and-reference-data/security-master-file-data) describes more than4million DTC/NSCC-eligible securities, daily updates, asset-class subscription choices, complete masters conditional on subscription; SFTP and selected Snowflake delivery. Useful for instrument reference mastering and issuer links if licensed, but no free complete master demonstrated.
- [Corporate-actions ISO20022 guide](https://www.dtcc.com/~/media/Files/Downloads/issues/Corporate%20Actions%20Transformation/Getting_Started_CA_ISO_20022.pdf) describes client subscription choices, MQ/NDM/FTP delivery, and sample messages by request. Public dictionaries/documentation do not make actual announcement data freely available.
- [Security Position Reports](https://www.dtcc.com/products-and-services/asset-services/issuer-services/security-position-reports) are for issuers, trustees and approved third-party agents, showing DTC participants holding a security. This is neither a public download nor an ultimate beneficial-owner ledger.
- [Underwriting Data Report](https://www.dtcc.com/market-index-data/charts/underwriting-data-report) is public market volume/trend reporting; no issuer-level complete reference file verified.

## GMEI is retired; prefer existing GLEIF

[DTCC shutdown FAQ](https://www.dtcc.com/ust1/-/media/Files/PDFs/GMEI-Shutdown-FAQ) confirms portal closed July27,2023, exit August22,2023, LEIs transferred to other managing LOUs under GLEIF. Do not onboard GMEI as a new active independent source. [GLEIF API](https://www.gleif.org/en/lei-data/gleif-api/) already includes legal-entity reference information and mapped identifiers such as BIC/ISIN.

## Licensing / recommendation

Public access is not an open redistribution license. [DTCC terms](https://www.dtcc.com/terms), updated March11,2026, apply to site content and acknowledge separate agreements governing some material. No blanket open-data/CC license verified for DTCC public sources. Exact automation/redistribution rights remain a dataset-specific question.

Recommend first bounded profile of public member directories + membership notices, preserving source IDs, source dates and captured-file provenance. Use as Company role/alias evidence; keep reviewed matching and original SEC/GLEIF identity authority. Next investigate a small DDR sample only if Security/derivatives analytics enters scope. Do not ingest paid security master, positions or corporate-action services under a public-data assumption.

## Additional verified public reference lists

[DTC reference directories](https://www.dtcc.com/support/dtc-reference-directory) expose PDFs for limited-partnership deposit procedures, ownership certifications, and Section 3(c)(7) corporate/municipal issuers. The [3(c)(7) document](https://files.dtcc.com/download/assets/Corporate-And-Municipal-Reference-Directory.pdf/feb75dba369511f0a787c204a2f8334f) was readable through the web tool: 100 pages, CUSIPs and abbreviated security descriptions, document updated September 21, 2026 (landing page September 29). This is a selective securities list, not the complete eligible-security master. Proposed use: attach dated restriction/certification observations to already identified instruments; do not assume an abbreviated security description identifies a Company.

SEC corroboration: [Regulation SBSR final rule](https://www.sec.gov/files/rules/final/2015/34-74244.pdf), pp.169 and620, prohibits disseminating counterparty identity. Consequently, public swap observations do not establish named trading-counterparty relationships or holdings. Underlying-reference links need separate identifier validation.

## Anonymous access retest and scope decision

On October 9, 2026 an anonymous `curl` GET of the linked DTC participant XLSX
returned HTTP 200, MIME type `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`,
and 46,730 bytes. No credentials or cookies were supplied. The earlier Python
HTTP 403 does not establish a registration requirement; its exact cause remains
unconfirmed. This proves one public download, not ingestion or licensing qualification.

Operator keeps Security Position Reports and selected CUSIP lists in scope at
lower priority. The authoritative task checklist is
[DTCC enrichment](../../.planning/workstreams/dtcc-enrichment/TICKET.md).

The Security Master factsheet and product information contain no verified dollar
price. Request a DTCC quote for asset classes, standard versus premium update
frequency, delivery, internal use, redistribution and any separate identifier rights.
[Current factsheet](https://www.dtcc.com/reg-sci/-/media/Files/Downloads/Data-Services/Corporate-Actions-And-Reference-Data/Security-Master-File-Data-Factsheet.pdf),
[Data Services contact](https://www.dtcc.com/products-and-services/data-services).
