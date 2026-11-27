# No Snowflake resource monitor

Status: open
Type: task
Owner: claude (operator, 2026-11-27: "Why do we need to raise quote no need for resource monitor")

Operator, 2026-11-27: "Why do we need to raise quote no need for resource monitor". Ruling: the Snowflake account has
no resource monitor. What follows: the Terraform no longer defines one, and the access audit asks for none on
Snowflake. Nothing then stops Snowflake compute spend by itself; the account's statement timeouts stay, and spend is
read, not capped.

## Checklist

- [x] The monitor and its quota variable leave the Snowflake access root; the audit's Snowflake `CST` control and its evidence are removed, with the skills that name them (2026-11-27 13:51 ET)
- [ ] `DROP RESOURCE MONITOR EDGARTOOLS_PROD_MONITOR;` in Snowflake by an account administrator (the operator; an agent never uses that role)
- [ ] The mirror operator's warehouse answers: the mirror is listed
- [ ] `/code-review`, PR green and merged
- [ ] Learning → skill
