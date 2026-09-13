# Set the GLEIF MDM processing frequency

Type: grilling
Status: resolved
Blocked by: 06

## Question

Should each GLEIF Daily Delta Refresh rematch the full MDM entity universe, or
should matching and enrichment application use different scopes and cadences?

## Answer

The user accepted change-driven daily processing. A GLEIF Daily Delta Refresh
updates accepted links affected by the source delta and evaluates newly eligible
or materially changed MDM entities. It does not rematch the complete universe.
A GLEIF Candidate Backstop re-evaluates unresolved and unmatched entities each
week. A GLEIF Full Reconciliation proves complete source-to-MDM parity each
month.
