# 165: Quality cases show the engine's results

Priority: 165. Map: [Rebuild priorities](../map.md). Opened 2026-11-02 06:45 ET (same request as 163).

Type: task. Status: open. Blocked by: 163, 164.

## Question

The 29 cases have no pass or fail, so the Data Quality tab shows nothing run. Where does the engine record a failed check, and can the publisher send a result per case?

## Parts

- [ ] Find where the engine records failed checks (silver quality columns, the run report) and what a count per check looks like
- [ ] Decide with the operator whether results are sent by `publish` or by a separate command, since a result is a run, not a rule
- [ ] Send a result per case; read it back
- [ ] Learning → skill
