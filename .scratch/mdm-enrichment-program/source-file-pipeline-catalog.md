# MDM Enrichment source-file pipeline catalog

Date: 2026-09-13
Status: planning inventory; no implementation or production authorization

## Purpose

This catalog names each new GLEIF pipeline and every source-file family that it
may consume. It connects the external Source Authority file to GLEIF Evidence
Capture, Normalized Source Evidence, an MDM Enrichment Consumer, its Consumer
Checkpoint, and its publishing or Deferred Domain Evidence outcome.

One timestamped filename is only an example of a source publication. Pipeline
identity must use the native publication identity, declared inventory, content
hash, and capture run. It must not use a mutable download-page position or a
filename alone.

## Common file flow

```text
GLEIF publication discovery
        |
        v
Source Fetch Decision for each declared archive
        |
        v
Capture Facade -> exact ZIP in Temporary Bronze Stage -> Change Ledger
        |
        v
Verify archive hash, member inventory, CDF/parser contract, and record count
        |
        v
Normalized Source Evidence
        |
        +--> domain Consumer Candidate
        +--> Enrichment Stewardship Decision, when required
        +--> Accepted Binding or Deferred Domain Evidence
        |
        v
Consumer transaction + Consumer Checkpoint + MDM Commit Evidence
        |
        +--> Snowflake export
        `--> graph publication
        |
        +--> complete publication: retain as latest Source Artifact Archive copy
        `--> delta publication: delete Temporary Bronze only after every required
             consumer and downstream verification passes
```

GLEIF Evidence Capture downloads each source archive once. Company, Security,
Fund, Branch, Adviser, Audit Firm, Government Entity, International
Organization, Sole Proprietor, and Market/Trading Venue consumers read the same
Normalized Source Evidence. They do not download private copies of a shared
GLEIF publication.

## 1. Global LEI Index publication files

GLEIF publishes three Golden Copy file families in XML, CSV, and JSON. It also
publishes four time-window delta variants for each family. XML is the normative
CDF representation. GLEIF produces JSON and CSV from XML, and CSV can limit
repeated fields and omit extension information. The repository's frozen
research evidence uses JSON ZIP files. The accepted canonical production
representation is the exact XML ZIP. Production does not capture equivalent
JSON or CSV encodings as separate business publications.

Production discovery must use the official latest-publication endpoint:

`https://goldencopy.gleif.org/api/v2/golden-copies/publishes/latest`

The `leidata-preview.gleif.org` endpoint in the frozen September 2026 research
manifest is fixture provenance. It is not the planned production authority.

The patterns below use `{publication}` for `YYYYMMDD-HHMM`.

| Source-file family | CDF contract | Full archive pattern | Full member pattern | Records supplied |
| --- | --- | --- | --- | --- |
| Level 1 legal-entity records | LEI-CDF 3.1 | `{publication}-gleif-goldencopy-lei2-golden-copy.{json,csv,xml}.zip` | same stem without `.zip` | LEI, legal name, addresses, jurisdiction, legal form, entity category and status, registration and lifecycle evidence |
| Level 2 relationship records | RR-CDF 2.1 | `{publication}-gleif-goldencopy-rr-golden-copy.{json,csv,xml}.zip` | same stem without `.zip` | exact directional relationship type, endpoints, periods, relationship status, and registration evidence |
| Level 2 reporting exceptions | Reporting Exceptions 2.1 | `{publication}-gleif-goldencopy-repex-golden-copy.{json,csv,xml}.zip` | same stem without `.zip` | the child LEI, exception category, reason, and registration evidence |

### Daily files

The GLEIF Daily Delta Refresh consumes one 24-hour delta for each independent
family checkpoint:

- `{publication}-gleif-goldencopy-lei2-last-day.{json,csv,xml}.zip`
- `{publication}-gleif-goldencopy-rr-last-day.{json,csv,xml}.zip`
- `{publication}-gleif-goldencopy-repex-last-day.{json,csv,xml}.zip`

One scheduled run discovers one GLEIF release set. Level 1, relationship, and
reporting-exception artifacts retain independent family identity and
checkpoints. A consumer advances only when every family it declares as required
is verified. A failed family does not advance another family's Consumer
Checkpoint. Absence from one daily delta is not retirement evidence.

### Recovery files

If a 24-hour delta does not cover the last committed family checkpoint, the
pipeline may use a larger official delta only when its native metadata proves
continuous coverage:

| Recovery window | Level 1 | Relationships | Reporting exceptions |
| --- | --- | --- | --- |
| Seven days | `...-lei2-last-week.*.zip` | `...-rr-last-week.*.zip` | `...-repex-last-week.*.zip` |
| 31 days | `...-lei2-last-month.*.zip` | `...-rr-last-month.*.zip` | `...-repex-last-month.*.zip` |
| Complete baseline | `...-lei2-golden-copy.*.zip` | `...-rr-golden-copy.*.zip` | `...-repex-golden-copy.*.zip` |

The eight-hour `...-intra-day.*.zip` files exist, but the accepted operating
model does not schedule them. GLEIF retains the LastDay, LastWeek, and LastMonth
delta files for 31 days. A longer gap therefore requires a complete Golden Copy.
The monthly GLEIF Full Reconciliation uses the three complete Golden Copy
families.

The supported direct-download forms are:

```text
https://goldencopy.gleif.org/api/v2/golden-copies/publishes/{lei2|rr|repex}/latest.xml
https://goldencopy.gleif.org/api/v2/golden-copies/publishes/{lei2|rr|repex}/latest.xml?delta={LastDay|LastWeek|LastMonth}
```

## 2. Identifier-mapping publication files

GLEIF publishes mapping archives separately from the Golden Copy publication.
Each mapping has its own Source Publication, cadence, file identity, Consumer
Checkpoint, and recovery proof. It must not be inserted into the daily Company
job only because the file contains an LEI.

| Mapping pipeline | Source archive pattern | ZIP member pattern | Native cadence | Owning MDM route |
| --- | --- | --- | --- | --- |
| ISIN-to-LEI | `isin-lei-{timestamp}.zip` | `lei-isin-{timestamp}.csv`; `LEI,ISIN` | Daily | Security identifier to accepted issuer legal entity |
| BIC-to-LEI | `LEI-BIC-{date}.zip` | `lei-bic-{timestamp}.csv`; `LEI,BIC` | Monthly | Branch or accepted financial-organization identity; Adviser/Audit Firm when semantics apply |
| MIC-to-LEI | `LEI-MIC-{date}.zip` | `lei-mic-{timestamp}.csv`; `LEI,MIC` | Declared monthly; visible releases can be irregular or additional | Market/Trading Venue to accepted operating legal entity |
| OpenCorporates ID-to-LEI | `oc-lei-{timestamp}.zip` | `lei-oc-{timestamp}.csv`; `LEI,OpenCorporatesID` | Every two weeks | Corroborating Company source reference after accepted LEI routing |
| QCC Code-to-LEI | `LEI-QCC-{date}.zip` | `lei-qcc-{timestamp}.csv`; `LEI,QCC` | Monthly | Accepted Company or Government Entity source reference |
| GEM Entity ID-to-LEI | `LEI-GEM-{date}.zip` | `lei-gem-{timestamp}.csv`; `LEI,GEM` | Declared monthly; the new publication history is still irregular | Accepted Company or Government Entity source reference; never energy-asset ownership by itself |
| S&P CIQ Company ID-to-LEI | No approved public bulk archive | Weekly pairs in LEI Search; bulk file is subject to an S&P service contract | Weekly search surface | Conditional Company review evidence only; no pipeline until access and license gates pass |

Verified source examples on 2026-09-13 were:

| Mapping | Archive example | Member observed inside the archive |
| --- | --- | --- |
| ISIN | `isin-lei-20260913T071511.zip` | `lei-isin-20260913T071511.csv` |
| BIC | `LEI-BIC-20260828.zip` | `lei-bic-20260828T000000.csv` |
| MIC | `LEI-MIC-20260810.zip` | `lei-mic-20260810T120007.csv` |
| OpenCorporates | `oc-lei-20260902T125047.zip` | `lei-oc-20260902T125047.csv` |
| QCC | `LEI-QCC-20260901.zip` | `lei-qcc-20260901T000000.csv` |
| GEM | `LEI-GEM-20260825.zip` | `lei-gem-20260825T180400.csv` |

These examples confirm naming shape only. Each mapping publication is a complete
matched-pair snapshot, not a delta. The Source Family Registry must discover the
current publication and verify its manifest. It must not construct a URL from
the example date. The current official latest-download forms are:

```text
https://mapping.gleif.org/api/v2/isin-lei/latest/download
https://mapping.gleif.org/api/v2/bic-lei/latest/download
https://mapping.gleif.org/api/v2/mic-lei/latest/download
https://mapping.gleif.org/api/v2/oc-lei/latest/download
https://mapping.gleif.org/api/v2/qcc-lei/latest/download
https://mapping.gleif.org/api/v2/gem-lei/latest/download
```

## 3. Pipeline-by-pipeline file manifest

### Shared GLEIF baseline and GLEIF Full Reconciliation

Source files:

1. Complete Level 1 LEI-CDF Golden Copy archive.
2. Complete Level 2 RR-CDF Golden Copy archive.
3. Complete Level 2 Reporting Exceptions Golden Copy archive.

All three are captured. Each family has its own checkpoint and normalized
record inventory. The full set supplies the baseline used by every GLEIF-backed
consumer. It does not publish an MDM entity by itself.

### GLEIF Daily Delta Refresh

Source files:

1. Level 1 `last-day` archive.
2. Relationship `last-day` archive.
3. Reporting-exception `last-day` archive.

This pipeline updates source evidence for changed records. It evaluates only
accepted links affected by the delta and newly eligible or materially changed
MDM entities. It does not rematch the complete MDM universe.

### Company Legal-Entity Enrichment

Input evidence:

- Level 1 records classified and accepted as Company.
- `IS_DIRECTLY_CONSOLIDATED_BY` relationship records.
- `IS_ULTIMATELY_CONSOLIDATED_BY` relationship records.
- Direct- and ultimate-parent reporting exceptions.
- OpenCorporates ID-to-LEI mapping files at their native cadence.

The consumer does not ingest Fund, Branch, Government Entity, International
Organization, or Sole Proprietor records as Company. SEC remains the Source
Authority for CIK, filings, and reported financials.

### Security and Issuer Enrichment

Input evidence:

- ISIN-to-LEI CSV mapping publication.
- Level 1 record for the mapped issuer LEI.

The consumer may publish a Security identifier and typed issuer relationship
only when the Security and issuer identities are accepted. An ISIN is not a
Company attribute. The ISIN file is not complete legacy-ISIN coverage, so file
absence cannot retire an existing Security.

### Fund Legal-Entity Relationships

Input evidence:

- Level 1 Fund-category records.
- RR-CDF records with `IS_FUND-MANAGED_BY`, `IS_SUBFUND_OF`, or
  `IS_FEEDER_TO`.
- Applicable reporting exceptions retained at source grain.

This consumer does not reuse or reverse the SEC Form ADV `MANAGES_FUND`
relationship.

### Branch Legal-Entity Enrichment

Input evidence:

- Level 1 international-branch records.
- RR-CDF records with `IS_INTERNATIONAL_BRANCH_OF`.
- Applicable reporting exceptions.
- BIC-to-LEI mapping files when the BIC semantics resolve to the Branch or its
  accepted head office.

The consumer does not create a Company or a generic entity for a missing
endpoint.

### Adviser and Audit-Firm Legal-Entity Enrichment

Input evidence:

- Level 1 records for an independently accepted Adviser or Audit Firm.
- Applicable RR-CDF and reporting-exception evidence.
- BIC, QCC, or GEM mapping evidence only when the identifier semantics match the
  accepted domain.

IAPD and PCAOB remain their existing Source Authorities. An LEI mapping does not
duplicate the entity as a Company.

### Government Legal-Entity Enrichment

Input evidence:

- Level 1 records with the accepted Government Entity category.
- Applicable RR-CDF and reporting-exception evidence.
- QCC Code-to-LEI and GEM Entity ID-to-LEI files when their mapping semantics
  apply.

The consumer does not classify this evidence as Company.

### International-Organization Enrichment

Input evidence:

- Level 1 records with the accepted International Organization category.
- Applicable RR-CDF and reporting-exception evidence.

Unsupported endpoints remain Deferred Domain Evidence.

### Sole-Proprietor business-capacity boundary

Input evidence:

- Level 1 records with the Sole Proprietor category.
- Applicable relationship and reporting-exception evidence.

This remains a captured-only route until privacy and identity review allows a
consumer. An LEI does not establish unrelated natural-person identity.

### Market and Trading-Venue Enrichment

Input evidence:

- MIC-to-LEI CSV mapping publication.
- Level 1 evidence for the accepted operating legal entity.

MIC is a Market or Trading Venue code. It is not stored as a Company identifier.

### Identifier-mapping capture

The ISIN pipeline captures one complete CSV mapping snapshot daily. The BIC,
MIC, OpenCorporates, QCC, and GEM pipelines each capture one complete CSV
mapping snapshot at the source's native cadence. Each computes a Lifecycle Diff
against its own Pinned Silver Publication. A mapping disappears only after a
complete verified snapshot and domain-owned reconciliation. One mapping
pipeline cannot advance another pipeline's checkpoint.

### GLEIF Candidate Backstop

New source files: none.

The weekly backstop reads the current Normalized Source Evidence and rechecks
unresolved, unmatched, newly eligible, or materially changed MDM entities. It
must not download a second Golden Copy only to perform matching.

### Conditional S&P CIQ evaluation

New source files: none approved.

Weekly LEI Search pairs may support bounded research or stewardship review.
There is no production bulk pipeline until the Conditional Source Decision is
`adopt` and the service contract supplies approved bulk access, license,
immutable capture, cadence, replay, retention, and cost terms.

## 4. Required manifest for every file pipeline

Each Source Publication must record:

- source and publication family;
- native publication ID and publication time;
- discovery URL and immutable download URL;
- declared archive inventory and expected member names;
- archive byte count, content type, raw evidence hash, and read-back result;
- Temporary Bronze Stage identity and verified Source Artifact Archive object,
  when the artifact is a complete publication, including storage class,
  transition time, and checksum parity;
- for a delta, every required Consumer Checkpoint and downstream verification
  that must pass before Change-Ledger-authorized temporary-object deletion;
- every later physical location or storage-class transition and its authorized
  retention decision;
- format, CDF or mapping contract, parser version, and normalized record count;
- license or terms version and mapping certification status when applicable;
- root run, phase attempt, registry version, and Change Ledger evidence;
- previous committed publication, continuity proof, and selected recovery path;
- every record's terminal route: accepted, rejected, review, deferred, unchanged,
  superseded, or retired; and
- Consumer Checkpoint and downstream MDM, export, and graph counts when the
  consumer publishes.

## 5. Files that are not pipeline inputs

- GLEIF Concatenated Files are not part of the accepted Golden Copy operating
  path. They may be considered later only through a new source-family decision.
- Eight-hour intra-day delta files are not scheduled by the accepted daily
  model.
- CSV, XML, JSON, and RDF copies of the same Golden Copy must not all be captured
  as if they were different business publications.
- GLEIF API responses must not silently replace a missing publication file.
- S&P CIQ bulk data is not a source file until access and license are approved.
- Market data, sanctions, ESG, credit, and other commercial sources remain
  Conditional Enrichment Sources. They are not new data pipelines yet and have
  no approved file manifest.
- Documentation PDFs, factsheets, schema examples, and CSV import guides are
  parser and license references. They are not business-data inputs.

## 6. Specification decisions still required

The file inventory is complete enough to write the shared-foundation
specification, but it exposes decisions that the specification must close:

1. Select one canonical Golden Copy encoding. XML ZIP is the recommended
   normative and lossless production artifact. JSON ZIP is the current tested
   fixture. CSV is not recommended as the canonical evidence because it can
   limit repeated values and omit extension information.
2. Define the supported discovery interface and fail-closed behavior if the
   GLEIF download page and publication API disagree.
3. Define exact archive/member validation and decompression resource limits.
4. Bind each mapping's terms and certification version to the publication.
5. Define the approved alternative when a mapping source does not publish on
   its expected date.
6. Keep S&P CIQ bulk ingestion blocked until the Conditional Source Decision is
   `adopt`.

## Sources

- [GLEIF Golden Copy and Delta Files](https://www.gleif.org/en/lei-data/gleif-golden-copy/)
- [Download the GLEIF Golden Copy and Delta Files](https://www.gleif.org/en/lei-data/gleif-golden-copy/download-the-golden-copy)
- [GLEIF Golden Copy and Delta Files manual](https://www.gleif.org/lei-data/gleif-golden-copy/2022-02-23_gleif-golden-copy-and-delta-files_v2.2-final.pdf)
- [GLEIF Data Dictionary](https://www.gleif.org/lei-data/access-and-use-lei-data/gleif-data-dictionary/2025-11-18_gleif-data-dictionary_v1.2_final.pdf)
- [GLEIF LEI Mapping catalog](https://www.gleif.org/en/lei-data/lei-mapping)
- [ISIN-to-LEI files](https://www.gleif.org/en/lei-data/lei-mapping/download-isin-to-lei-relationship-files)
- [BIC-to-LEI files](https://www.gleif.org/en/lei-data/lei-mapping/download-bic-to-lei-relationship-files)
- [MIC-to-LEI files](https://www.gleif.org/en/lei-data/lei-mapping/download-mic-to-lei-relationship-files)
- [OpenCorporates ID-to-LEI files](https://www.gleif.org/en/lei-data/lei-mapping/download-oc-to-lei-relationship-files)
- [QCC Code-to-LEI files](https://www.gleif.org/en/lei-data/lei-mapping/download-qcc-to-lei-relationship-files)
- [GEM Entity ID-to-LEI files](https://www.gleif.org/en/lei-data/lei-mapping/download-gem-to-lei-relationship-files)
- [S&P CIQ Company ID-to-LEI relationship](https://www.gleif.org/en/lei-data/lei-mapping/s-and-p-c-i-q-company-id-to-lei-relationship)
- [Accepted GLEIF identifier-mapping routing](../gleif-company-augmentation/research/11-gleif-identifier-mapping-routing.md)
- [Accepted GLEIF relationship routing](../gleif-company-augmentation/research/10-gleif-relationship-routing.md)
