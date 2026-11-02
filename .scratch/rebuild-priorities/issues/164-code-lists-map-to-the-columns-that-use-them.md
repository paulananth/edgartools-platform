# 164: Code lists map to the columns that use them

Priority: 164. Map: [Rebuild priorities](../map.md). Opened 2026-11-02 06:45 ET (same request as 163).

Type: task. Status: open. Blocked by: none.

## Question

Of 30 lineage edges, 11 carry column mappings. The other 19: 13 link a code list to the silver table that uses it, and 6 link a captured file feed to the dataset that reads it. Which can show columns?

Answer: the 13 code-list edges can (the list's `code` column to the silver column that holds those codes). The 6 file edges stay table to table, because a file feed has no columns.

## Parts

- [ ] GoF consult before the code
- [ ] The 13 code-list edges carry `code` to the using column (test: one edge in a copy of the rules)
- [ ] `check` matches after a publish; the live edges read back with columns
- [ ] Learning → skill: `skills/openmetadata/SKILL.md` says which edges carry columns and why the file edges do not
