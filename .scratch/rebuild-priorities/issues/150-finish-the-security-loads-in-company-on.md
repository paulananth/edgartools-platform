# 150: Finish the Security loads in company-on

Priority: 150. Map: [Rebuild priorities](../map.md). Opened 2026-10-29 18:21 ET, moved out of ticket 120
(operator, 2026-10-29: "Stop, count, close (Recommended)": ticket 120 closes on the counts already loaded, and
the rest of the load moves here).

Type: task. Status: claimed (Claude, 2026-11-01 15:41 ET, branch `claude/t150-merge-memory`). Blocked by: none.

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

- [ ] Root cause of the merge's memory (measured 2026-10-29 20:35-21:55 ET, one bundle at a time, memory sampled every 15 s; then stopped on the operator's words "this is enough move on", 21:58 ET): 14 open runs, 0 finished; 4 merges killed with status -9, 3 "destination authority expired before save", 1 stopped by the deadline, 9 never started. No merge was seen above 1.55 GB, and free memory never fell under 19%, so a memory kill by the machine is not shown by these samples (a rise between two samples is not ruled out); what sends the kill is open. Next step: measure one open run's merge (peak memory, time, rows), against the
  machine's free memory with the shared server running
- [ ] Root cause of "destination authority expired before save": the permission's lifetime against the merge's
  time, and whether the heartbeat renews it. Read in the code (2026-10-29 19:09 ET), to be confirmed by the
  measurement: the heartbeat renews the lease every `heartbeat_seconds` and writes the new proof into the envelope
  (`workers/__main__.py`, `Renewal`), but one save transaction records the proof it started with and, at commit,
  requires that same proof unexpired (`adapter_sql.py`, the `destination_authority_expired_before_save` guard). So
  one batch's save that runs longer than the lease fails, renewed or not. OpenFIGI's `mastering` targets set no
  `lease_seconds`, so 120 s; N-PORT Security sets 900 (ticket 120, for FIGI steps since removed). A merge unit is a
  bundle's prepared manifest: 53 batches of about 805 Securities (bundle 7: 31.6 MB), each batch its own
  transaction (`execution.execute_manifest`). Whether a batch's save is slow by itself or slowed by memory pressure
  is what the measurement decides
- [ ] Evidence for the memory: one OpenFIGI merge worker held about 790 MB 20 s after it started and about 1.0 GB at
  21 min (2026-10-29, `ps`), so its memory grows over the batches; `execute_manifest` keeps every batch's result
  until the end (`committed`). Measure what each result holds
- [x] The tail of a merge (start check, receipt, run report) reads one batch at a time: bundle 10's receipt 493 s to 29 s, footprint 9.5 GB to 1.7 GB, receipt byte-identical to the stored one; publication check 38 s, 960 MB (2026-11-01 16:22 ET; profiled on the real bundle; storage-adapter tests on MySQL; PR below)
- [ ] The fix, with its test (a merge of the measured size fits, and saves inside its permission)
- [ ] Finish the OpenFIGI load: the same command finishes its open runs first
- [ ] The N-PORT Security load (2026 Q2)
- [ ] Counts; no identifier on two masters
- [ ] Learning → skill (data-operations, "Fit a load into the window": what a merge needs on this machine)

## Measurement (Claude, 2026-11-01 15:45-16:07 ET)

Bundle 10 of the OpenFIGI load (52 batches, all saved on 2026-10-29 08:50-09:17 ET, 27 min; no receipt written):

- Nine of the merges that "failed" had saved all 52 batches (25-33 min each); only 3 bundles have a receipt. The failure is after the saves, in the tail the merge worker runs once the batches are saved.
- The tail reads every saved batch's intent (`read_batches`, 400 per chunk, so all 52 in one `.all()`): 2,747 MB for this bundle (biggest batch 69 MB; 668 batches hold 32 GB of intent). Measured alone: `read_batches` 217 s, `receipt()` 273 s (reads them again), 493 s in total. Peak resident 813 MB, but macOS reports a peak memory footprint of 9.5 GB (compressed pages), the same footprint that sends an 8 GB machine into swap and a kill.
- `execute_manifest` calls `batches()` (the same read) at its start, and the verifier calls `receipt()` again: three full reads of the bundle's intents per merge.
- Not yet shown: that the saves themselves are slow ("destination authority expired before save"); a first-attempt merge was not measured.
