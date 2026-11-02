# 164: Code lists map to the columns that use them

Priority: 164. Map: [Rebuild priorities](../map.md). Opened 2026-11-02 06:45 ET (same request as 163).

Type: task. Status: resolved. Blocked by: none.

## Question

Of 30 lineage edges, 11 carry column mappings. The other 19: 13 link a code list to the silver table that uses it, and 6 link a captured file feed to the dataset that reads it. Which can show columns?

Answer: the 13 code-list edges can (the list's `code` column to the silver column that holds those codes). The 6 file edges stay table to table, because a file feed has no columns.

## Parts

- [x] GoF consult before the code: leave it; `uses` keeps the column beside the table, no new class (2026-11-02 07:29 ET)
- [x] The 13 code-list edges carry `code` to the using column (`test_a_code_list_edge_maps_the_code_to_the_column_that_holds_it`, 2026-11-02 07:29 ET)
- [x] `check` matched after a publish; 13 of 13 code-list edges read back with columns (2026-11-02 07:31 ET)
- [x] Learning → skill: `skills/openmetadata/SKILL.md` says which edges carry columns and why the file edges do not (2026-11-02 07:31 ET)
