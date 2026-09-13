# Select the Golden Copy representation and completeness boundary

Type: grilling
Status: open
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

Recommendation: retain the exact XML ZIP as the normative, lossless production
Bronze Artifact; treat the current JSON ZIP corpus as a frozen research fixture;
model the GLEIF release set as three linked family publications so each family
retains independent recovery while a consumer cannot advance until all of its
declared required families are verified.
