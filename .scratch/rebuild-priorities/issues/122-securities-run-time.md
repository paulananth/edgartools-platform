# 122: Make the Securities run faster

Priority: 122. Map: [Rebuild priorities](../map.md). Found by ticket 120's
test run (operator, 2026-10-20: "why securities takes so long give me profile
of time taken", then "convert this to a document that we can visit later for
optimization").

Type: task. Status: open (to revisit). Blocked by: none. Related:
[121](121-another-runs-reading-over-time.md) (rechecking cost, the 256-unit list).

## The profile (2026-10-20, measured)

The Securities test run (`mastering`, the whole 2026 Q2 N-PORT quarter) took
2 h 20 min for pass 1 (00:01–02:21 ET, store `sec-test`, run
`f928414a`). Each step's time is the gap between its unit's verification and
the previous step's, from Bookkeeping's journal:

| Stage | Steps (minutes) | Total | What it does |
|---|---|---|---|
| Read the quarter | identifiers 4.2, submissions 0.0, **holdings 13.3**, issuers 3.6 | 21 m | Reads every holding of the quarter's N-PORT file |
| Find and reduce | cusips_found 6.2, isins_found 1.2, reduce 2.0, issuer_reduce 0.4, pairs 0.7 | 10.5 m | Holdings against OpenFIGI's answers, then reduced |
| OpenFIGI agreement | figi_pairs 5.3, agree 4.8, offers 4.9, attach 9.2 | 24 m | Which ISIN goes with which CUSIP |
| Build records | combine 11.2, record 10.3, prepare 9.9 | 31 m | The 383,612 Security records |
| **Merge into MDM** | **merge 36.3**, processed 0.0 | 36 m | 383,612 records written into MDM, about 176 a second |
| End of run | (after processed, before the run is complete) | 16 m | Not yet broken down |

Each step had exactly one unit and one attempt.

## Why it is slow

1. **Each step is one job.** The quarter arrives as one zip, so every step has
   one unit. The eight parallel workers have nothing to share, so the 18
   steps run one after another.
2. **Bookkeeping's checks grow after OpenFIGI's answers come in.** From
   `cusips_found` on, every step reads those answers. Each claim and each
   report rechecks the history behind about 480 OpenFIGI answer units (16
   request files each): 73 s to claim and 73 s to report at `figi_pairs`,
   against about 20 s of work. The cost repeats in each of the ten steps that
   follow; `combine`'s report in pass 2 ran over 5 minutes.
3. **The merge writes records one by one.** 36 minutes for 383,612 records.

## Not a cause: pass 2's sleep

Pass 2 took longer because the Mac's battery reached 1% and it went into
low-power sleep from 02:46 to 05:55 ET; `caffeinate` cannot prevent that. The
`holdings` unit lost its lease and ran again (two attempts). Long local runs
need the Mac on power.

## Ideas to test (none decided)

- [ ] Measure the split between work and Bookkeeping's checks for every step,
      not only `figi_pairs` (a process sample every 2 s during pass 2:
      `combine`, `record`, `prepare`, `merge`)
- [ ] Recheck another run's units once per run, not on every claim and report
      (ticket 121, "Rechecking cost"); expected saving up to ~2–4 min a step
      over ten steps
- [ ] Split the quarter into several units at the reading steps (`holdings`,
      `issuers`), so parallel workers share the work
- [ ] Merge in sets of records rather than one by one, within the
      `mdm-engineering` skill's rules (the Merge Stage record by record is a
      rule today: change it only with the operator)
- [ ] Find what the 16 minutes after `processed` are
- [ ] Learning → skill
