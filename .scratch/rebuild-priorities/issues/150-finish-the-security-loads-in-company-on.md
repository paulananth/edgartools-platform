# 150: Finish the Security loads in company-on

Priority: 150. Map: [Rebuild priorities](../map.md). Opened 2026-10-29 18:21 ET, moved out of ticket 120
(operator, 2026-10-29: "Stop, count, close (Recommended)": ticket 120 closes on the counts already loaded, and
the rest of the load moves here).

Type: task. Status: open. Blocked by: none.

## Question

Ticket 120 switched Securities on in `company-on` and started its loads: OpenFIGI's own Security records
(capture run `openfigi-2026q2-nport`, 7,714 documents in 16 bundles), then N-PORT Security (2026 Q2, capture
run `sec-nport-2026q2`). Only the merge stage failed; every bundle's reading and preparation finished.

- **First attempt** (06:38-10:50 ET): 4 bundles at once on the 8 GB machine (Docker's VM takes 4 GB). Bundle
  3 finished; 15 failed in `mdm.merge`: 10 "Prepared state changed; re-assess" (four bundles merging into the
  same Securities), 4 killed for memory (status -9), 1 "Invalid name-index coverage" (the index then checked
  consistent; its rebuild had nothing to do).
- **Second attempt** (13:20-18:20 ET): one bundle at a time, 2 workers, 300 minutes. Of the 15 open runs, 1
  finished (its merge 39 min); 6 merges were killed for memory (status -9) even alone; 3 failed
  "destination authority expired before save" (the merge outlived its permission to write); 1 was stopped by
  the time limit; 4 never started.

Why does one OpenFIGI merge need more memory than the machine has, and outlive its write permission, when it is
the only merge running? Fix the cause, then finish the open runs and N-PORT Security.

## Parts

- [ ] Root cause of the merge's memory: measure one open run's merge (peak memory, time, rows), against the
  machine's free memory with the shared server running
- [ ] Root cause of "destination authority expired before save": the permission's lifetime against the merge's
  time, and whether the heartbeat renews it
- [ ] The fix, with its test (a merge of the measured size fits, and saves inside its permission)
- [ ] Finish the OpenFIGI load: the same command finishes its open runs first
- [ ] The N-PORT Security load (2026 Q2)
- [ ] Counts; no identifier on two masters
- [ ] Learning → skill (data-operations, "Fit a load into the window": what a merge needs on this machine)
