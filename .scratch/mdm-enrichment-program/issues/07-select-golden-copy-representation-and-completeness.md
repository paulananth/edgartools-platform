# Select the Golden Copy representation and completeness boundary

Type: grilling
Status: resolved
Blocked by: 06

## Question

Which one of GLEIF's XML, JSON, or CSV Golden Copy representations becomes the
canonical production Bronze Artifact, and does one release set form one
three-family Source Publication or three linked family publications with a
consumer-declared completeness gate?

The decision must preserve independent Level 1, relationship, and
reporting-exception checkpoints, define fail-closed behavior when discovery and
download metadata disagree, and prevent equivalent encodings from becoming
duplicate business publications.

## Answer

Use the exact XML ZIP as the normative, lossless production artifact. The
current JSON ZIP corpus remains a frozen research fixture. CSV and JSON copies
of the same Golden Copy are not additional business publications and are not
captured by the production path.

Model the GLEIF release set as three linked publication families:

1. Level 1 LEI legal-entity records advance independently.
2. Level 2 Relationship Records and Level 2 Reporting Exceptions retain their
   own artifact identities, but form one coordinated completeness unit. Neither
   checkpoint advances unless both artifacts are verified.
3. ISIN, BIC, MIC, OpenCorporates, QCC, and GEM identifier mappings are six
   independent complete-snapshot families. Each owns its native cadence,
   checkpoint, continuity proof, recovery, and domain route.

A failure in one independent family cannot roll back or advance another. The
coordinated Release 1 gate still waits for every mandatory family and consumer.

Accepted by the user during the 2026-09-13 Wayfinder session.
