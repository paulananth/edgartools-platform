# 165: Quality cases show the engine's results

Priority: 165. Map: [Rebuild priorities](../map.md). Opened 2026-11-02 06:45 ET (same request as 163).

Type: task. Status: open, blocked on a data source for results. Blocked by: none.

## Question

The 29 cases have no pass or fail, so the Data Quality tab shows nothing run. Where does the engine record a failed check, and can the publisher send a result per case?

## Parts

- [x] Found where the engine records failed checks (2026-11-02 08:01 ET): a silver table's `quality` column lists the failed check ids per flagged row; a source check with `on_fail: exception` sets the record aside with reason `quality_<id>` in MDM. Local state: no silver store is connected (the connection files only unset it), and the shared MDM store shows no exception or quality table to the verifier login. The only measured counts in the repo are `failed_rows` on OpenFIGI profile proposals, which are not configured cases
- [x] Decided with the operator (2026-11-02 08:01 ET): `publish` sends the results ("Should publish send the results Yes")
- [ ] Choose the results source (see the question on this ticket), then send a result per case from `publish`; read it back
- [ ] Learning → skill
