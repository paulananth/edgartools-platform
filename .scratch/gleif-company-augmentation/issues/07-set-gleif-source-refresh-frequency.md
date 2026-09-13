# Set the GLEIF source refresh frequency

Type: grilling
Status: resolved
Blocked by: 06

## Question

Should the platform consume each eight-hour GLEIF publication, one 24-hour
delta daily, or refresh less frequently?

## Answer

The user accepted one GLEIF Daily Delta Refresh using the 24-hour Level 1,
relationship, and reporting-exception deltas, plus one GLEIF Full
Reconciliation each month. The platform will not poll all three daily Golden
Copy publications. GLEIF may receive issuer changes with up to a 24-hour delay,
so three daily loads would add work without assuring materially fresher source
evidence.
