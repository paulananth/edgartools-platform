# 200: May an OpenFIGI name find a Company and wait?

Priority: 200. Map: [Rebuild priorities](../map.md). Opened 2026-11-09 08:28 ET (operator: "Agreed create a ticket", after the question whether OpenFIGI should be part of Company mastering).

Type: grilling, with a measurement first. Status: open. Blocked by: none.

## Question

Today OpenFIGI is not a Company source. It creates Securities, and a Security reaches its issuer through an `ISSUED_BY` link on the issuer LEI. Should an OpenFIGI issuer name be allowed to find an existing Company and wait (`on_no_match: wait`), and never create one?

## Why it is not recommended now

- OpenFIGI carries no CIK and no LEI. Every Company matching rule joins on an identifier.
- The operator's rule is that name matching is the last resort, only when no identifier exists.
- An OpenFIGI name is a security's name, not a legal entity's, and has no jurisdiction or postal code to back it, which the GLEIF name rules do have.
- The `ISSUED_BY` link through the issuer LEI already reaches the Company.

## Method, if the operator wants it

Measure the match rate on a sample chosen by kind, before any rule is written (operator: "sample before running everything"). Count matches that are right, wrong and ambiguous against Companies that already hold a CIK or LEI. Counts only in committed files. No provider request.

The operator's word is needed to switch any rule on.

## Checklist

- [ ] Take the operator's decision: leave OpenFIGI out (the current rule), or measure the match rate first.
- [ ] If measured: choose a sample by kind and count right, wrong and ambiguous matches.
- [ ] If the rate is good enough: write the find-and-wait rule in a copy of the policy and test both source orders and a second pass.
- [ ] Learning → skill: name the skill line this ticket changed, or write "none".
