---
plan_id: 10-01
status: complete
completed_date: 2026-06-05
---

## Summary

Acquired one real Form ADV XML for Vanguard Group Inc (CRD 105958) from the SEC FOIA bulk CSV
dataset (IA_ADV_Base_A, FilingID=1919760, filed 2024-12-18) and uploaded it to dev S3 bronze
at the canonical primary_doc.xml path. One private fund (CSF PRIVATE FUND) was present in
the Schedule D 7B1 data, so sec_adv_private_fund will have > 0 rows in Wave 2.

## Key Files Created
- s3://edgartools-dev-bronze-077127448006/warehouse/bronze/filings/sec/cik=105958/accession=ADV-105958-20241218/primary_doc.xml (uploaded)
- .planning/workstreams/neo4j-pipe/phases/10-live-adv-backfill-validation/10-VALIDATION-NOTES.md (created)

## Wave 2 --artifact String
ADV-105958-20241218,ADV,s3://edgartools-dev-bronze-077127448006/warehouse/bronze/filings/sec/cik=105958/accession=ADV-105958-20241218/primary_doc.xml,105958

## Acquisition Method
sec-bulk-csv -- SEC FOIA Form ADV Part 1 bulk data (https://www.sec.gov/foia-services/frequently-requested-documents/form-adv-data).
Data sourced from IA_ADV_Base_A (2011-2024 range), most recent filing for CRD 105958 dated 2024-12-18.
Private fund (CSF PRIVATE FUND, Hedge Fund, Cayman Islands) sourced from IA_Schedule_D_7B1.

## Self-Check: PASSED
- [x] 10-VALIDATION-NOTES.md "## ADV Bronze Acquisition" section written with method/source/accession/CIK
- [x] aws s3 ls confirms primary_doc.xml exists under cik=105958 with nonzero size
- [x] read_bytes via warehouse adapter returned nonzero bytes (681 bytes)
- [x] Wave 2 --artifact string recorded verbatim
