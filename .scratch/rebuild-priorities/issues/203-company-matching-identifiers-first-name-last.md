# 203: Company matching, identifiers first and name last

Priority: 203. Map: [Rebuild priorities](../map.md). Opened 2026-11-09 11:32 ET (operator: "Agreed what is the current proposal? Companies must be mastered name, former name and please is an approved rule of no other identifiers available"). Follows ticket 202.

Type: grilling, with a measurement. Status: open. Blocked by: none.

## Question

What is the one order in which a Company is matched, and which rules sit in it?

## Proposal

1. **Identifier first.** CIK (SEC and N-PORT registrant), CRD and BD number (ADV), LEI (GLEIF and ADV custodian). A record that holds an identifier is matched by it alone.
2. **A new identifier rule, for the operator's word:** an N-PORT registrant's stated LEI joins the GLEIF record with the same LEI. Today that LEI is a lookup only (operator, 2026-09-26: "lookup only", with "a matching rule on any of these IDs can be proven and approved later"). The reversal covers that one ID.
3. **Name last, an approved rule only where no other identifier is available:** name, former name and place (jurisdiction, postal code or city), kept as one rule family. A record that holds an identifier is never matched by name.
4. **Name Count inside the GLEIF merge** (ticket 202), as its uniqueness guard.

## Measured today (read-only, counts only, 2026-11-09 11:32 ET, local store)

- N-PORT registrant records: 5,841; 5,829 state an LEI; 1,939 distinct LEIs.
- 92 of those LEIs (276 records) equal a GLEIF record already in the store. All 276 GLEIF records wait with no Company today; none is on a Company.
- The loaded GLEIF scope was built from issuer LEIs, not registrants', so the other 1,847 registrant LEIs are not in the store. They are in the full GLEIF file, which a scope of the registrants' LEIs would load.
- Former names are used by no Company matching rule today.
- GLEIF records attached to a Company: 3,297 of 24,591 loaded LEIs.

## Checklist

- [x] Operator's word on reversing "lookup only" for the N-PORT registrant LEI (proposal item 2): given 2026-11-10 07:55 ET ("Master it ;consider it a source"), read as: the registrant LEI is searched like any source's identifier. Built under the remaining parts.
- [ ] Count the registrant LEIs against the full GLEIF file, from a scope of those 1,939 LEIs: how many equal a GLEIF LEI, and how many are the same entity by name and place (counts only).
- [ ] Write the LEI rule, declared and not switched on, in a copy of the policy; test both source orders and a second pass; the limited test is the proof.
- [ ] State "no other identifier available" as one precondition shared by every name rule (it exists today as `holds_no_other_lei@1` for LEI only), and add former name to the name rule family with its own proof.
- [ ] Decide whether the adviser's stated LEI (Form ADV filings, 7,246 records) and the N-PORT fund series LEI (25,848 records) join the GLEIF record with the same LEI, as the registrant LEI does. Found by ticket 204's list of keys stored and never searched, 2026-11-09 18:49 ET.
- [ ] Learning → skill: name the skill line this ticket changed, or write "none".
