Type: grilling
Status: open
Blocked by: 03
Labels: `wayfinder:grilling`

# Decide OpenMetadata Projection and Readback for MDM Quality

## Question

How should Bookkeeping-admitted MDM outcomes map to the existing OpenMetadata
test cases and per-load result history?

Specify the stable mapping from an admitted check to its catalog test case,
including the source asset or master table it describes; which per-run status,
counts, failure action, and rule version are published; how exact timestamped
readback proves the result; and how replay avoids duplicate or synthetic
results. Reuse the shipped API/UI and the verified Silver publication path;
OpenMetadata remains the results viewer, not the execution engine.

The answer should identify the specific check/readback proof needed for
Company, Person, and Security and explain how incomplete evidence remains
visibly unconfirmed.
