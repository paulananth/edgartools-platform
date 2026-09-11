# Decide whether bronze digest requires a contract version bump

Type: grilling
Status: open
Blocked by: 03

## Question

[Encode Bronze evidence identity in the Decision Watermark](03-encode-bronze-in-decision-watermark.md)
made a digest of ordered unique Bronze artifact hashes a required watermark
component and a READY/agent-grade gate. Python and the SQL sketches still
carry `decision_contract_version = "1"` from persist-only Ticket 09.

Does that semantic change bump Decision Contract Version before the first
READY publication, or does `"1"` remain until some other breaking shape
change?

Decide:

1. Keep `"1"` until the first live publication (bronze digest is a correction
   of an unpublished sketch).
2. Bump now (for example `"2"`) because agent-grade semantics changed.
3. Defer the number to the publication-writer ticket and only lock the bump
   rule (what counts as breaking).

Predecessor Ticket 09 shipped version `"1"` with persist-only bronze. This
ticket does not reopen persist-only.
