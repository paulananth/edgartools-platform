# Decide the GLEIF publication-family taxonomy for the shared foundation

Type: grilling
Status: open
Blocked by: none

## Question

The GoF review's Appendix C item 4 asks for the publication-family taxonomy
underneath the generic "source publication" aggregate — i.e., what counts as
one distinct publication family for GLEIF at the *foundation* level (not
Company-consumer-specific).

The [GLEIF MDM enrichment evidence](../gleif-company-augmentation/map.md)
map already made three adjacent decisions at the Company-consumer level that
this ticket needs to generalize, not re-decide:

- [Ticket 07](../gleif-company-augmentation/issues/07-select-golden-copy-representation-and-completeness.md):
  coordinate Relationship Records with Reporting Exceptions inside the same
  Golden Copy publication; six identifier mappings are independently
  checkpointed.
- [Ticket 09](../gleif-company-augmentation/issues/09-lock-shared-gleif-capture-boundary.md):
  capture all Level 1, relationship, and exception source evidence once.
- [Ticket 11](../gleif-company-augmentation/issues/11-decide-gleif-identifier-mapping-routing.md):
  only ISIN is daily; OpenCorporates is bi-weekly; BIC/MIC/QCC/GEM are
  monthly; S&P CIQ is deferred.

Does the foundation-level publication-family taxonomy become exactly: **(a)**
GLEIF Level 1 + Relationship Records + Reporting Exceptions as one Golden
Copy publication family (captured/checkpointed together, matching ticket 07),
plus **(b)** one independent publication family per identifier mapping
(ISIN, OpenCorporates, BIC, MIC, QCC, GEM, deferred CIQ), each on its own
cadence per ticket 11 — or does the foundation need a different split?

## Comments
