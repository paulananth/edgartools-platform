# 16: Master ids and links as joins inside the data database

Status: open
Type: grilling

Follow-up named by hosted-mirroring ticket 04 and carried by ticket 14. Nothing is decided yet.

## Question

MDM, RDM and silver now share one data database (schemas `mdm`, `rdm`, `silver`). A silver table with an MDM id column is filled from the
golden records, and a relationship links two masters. Should the master id on a silver row, and a link between two masters, be read as a join
inside the data database (so the mirror carries the tables and Gold joins them), or stay written onto the row by a step of the load?

## Checklist

- [ ] Read how the id is filled and the links are written today, and what Gold reads from the mirror
- [ ] Decide with the operator: join in the data database, or keep the written id; one question at a time, with a recommendation
- [ ] If a join: name the tables, keys and the Gold view change as a code ticket; if not: record why
- [ ] Learning → skill: name the skill line this ticket changed, or "none"
