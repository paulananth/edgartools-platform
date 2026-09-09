# Confirm final classification approach

Type: grilling
Status: resolved
Blocked by: 01

## Question

Ticket 01's research recommends *not* adding NAICS or GICS, and instead
deriving SIC's own native hierarchy (Division/Major Group/Industry
Group) from the `sic_code` EdgarTools already has. This is a genuinely
different answer than the map's original framing ("which system: NAICS,
GICS, or another"), so it needs explicit user sign-off before this map
can close: does the user accept this recommendation as the map's
decision, or want a different path (adding NAICS anyway with an
approximate/derived label, pursuing GICS despite the licensing cost,
or something else)?

## Answer

User accepted Ticket 01's recommendation: derive SIC's own native
hierarchy (Division/Major Group/Industry Group) from the existing
`sic_code`, and do not add NAICS or GICS. This closes the map -- the
destination (a decision on classification approach) is reached. A
follow-up build effort would implement the derivation (new MDM company
fields, the Division range-lookup table) and is out of scope for this
map per its own Notes (decision only, not execution).
