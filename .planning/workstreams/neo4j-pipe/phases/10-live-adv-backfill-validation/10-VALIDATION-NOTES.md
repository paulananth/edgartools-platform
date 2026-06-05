# Phase 10: Live ADV Backfill Validation Notes

## ADV Bronze Acquisition

**Method:** sec-bulk-csv
**Source:** SEC FOIA Form ADV bulk data download
**Source URL:** https://www.sec.gov/foia-services/frequently-requested-documents/form-adv-data
**Data file:** adv-filing-data-20111105-20241231-part1.zip / IA_ADV_Base_A_20111105_20241231.csv
**Private fund data:** adv-filing-data-20111105-20241231-part2.zip / IA_Schedule_D_7B1_20111105_20241231.csv
**Adviser:** THE VANGUARD GROUP, INC. / VANGUARD GROUP INC
**CRD:** 105958
**SEC File Number:** 801-11953
**Filing Date:** 2024-12-18 (most recent filing, FilingID=1919760)
**Accession:** ADV-105958-20241218

**Note:** Vanguard's December 2024 ADV Part 1 filing was extracted from the SEC FOIA bulk CSV dataset.
One private fund (CSF PRIVATE FUND) was present in IA_Schedule_D_7B1 for this filing.
The sec-bulk-csv method uses real Form ADV Part 1 data from all registered investment advisers,
filtered for CRD 105958. Private-fund detail (Schedule D 7B1) IS available for this filing.

## S3 Bronze Upload

**S3 URI:** s3://edgartools-dev-bronze-077127448006/warehouse/bronze/filings/sec/cik=105958/accession=ADV-105958-20241218/primary_doc.xml
**CIK:** 105958
**FORM:** ADV
**Size:** 681 bytes
**Verified:** aws s3 ls confirms one primary_doc.xml with nonzero size

## Storage Adapter Readability

read_bytes returned 681 bytes for the S3 URI above. Exit 0. ✓

## Wave 2 --artifact String

ADV-105958-20241218,ADV,s3://edgartools-dev-bronze-077127448006/warehouse/bronze/filings/sec/cik=105958/accession=ADV-105958-20241218/primary_doc.xml,105958
