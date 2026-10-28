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

## Work against checks (measured, pass 2, 2026-10-20 06:33–07:47 ET)

A sample every 2 s of the run's processes over the last steps of pass 2
(`combine`, `record`, `prepare`, `merge`, `processed`, the run's end): 74
minutes, of which **10.5 minutes were the steps' own work**.

| Step | Claim | Work | Report | Verify |
|---|---|---|---|---|
| combine (with attach's tail) | 2.4 m | 3.3 m | 2.8 m | 13.1 m |
| record | 2.6 m | 0.8 m | 2.5 m | 5.3 m |
| prepare | 2.3 m | 0.5 m | 2.2 m | 5.0 m |
| merge | 2.4 m | 5.9 m | 2.2 m | 4.6 m |
| End of run (`finalize`) | | | | 15.8 m |

- Each step pays about 2.4 min to claim, 2.4 min to report and 5 min to
  verify, whatever its work: Bookkeeping rechecking the history behind
  OpenFIGI's answers each time. That is **48 of the 74 minutes**.
- The **16 minutes at the end** are `bookkeeping finalize`, which checks the
  whole run again the same way.
- pass 2's merge took 5.9 min against pass 1's 36 min, since pass 2 changes
  nothing; the first load's merge is real work.

## Not a cause: pass 2's sleep

Pass 2 took longer because the Mac's battery reached 1% and it went into
low-power sleep from 02:46 to 05:55 ET; `caffeinate` cannot prevent that. The
`holdings` unit lost its lease and ran again (two attempts). Long local runs
need the Mac on power.

## OpenFIGI's merge joining Securities (measured 2026-10-20 19:36–20:44 ET, `sec-test`)

One CUSIP slice, 49,082 records each joining an existing Security with its listings (158,554 rows): the merge took about 50 minutes, about 16 records a second. At that rate the quarter's OpenFIGI records (about 383,000 by CUSIP and 33,000 by ISIN) take about 7 hours of merge in `company-on`. "Merge in sets of records" (below) is the idea it adds weight to.

## A repeated delivery is slow (measured 2026-10-28 11:53 ET, ticket 138's limited test)

350 N-PORT Security records (300 CUSIPs, 50 ISIN-only) into a fresh disposable
MDM in batches of 250: the first pass 8 s; the same records again, changing
nothing, 172 s. Reading the 350 Securities back through `ContractReader`
(`snapshot_page`, pages of 1,000) took about 5 minutes over two reads. Not yet
profiled.

## Ideas to test (none decided)

- [x] Measure the split between work and Bookkeeping's checks (2026-10-20 07:55 ET): sampled over pass 2's last steps, above; checks are 48 of 74 minutes, `finalize` 16
- [ ] Recheck another run's units once per run, not on every claim, report,
      verify and finalize (ticket 121, "Rechecking cost"); measured cost about
      10 min a step over the ten steps that read OpenFIGI's answers, plus
      `finalize`'s 16 min: roughly 1.5 to 2 hours of the run
- [ ] Split the quarter into several units at the reading steps (`holdings`,
      `issuers`), so parallel workers share the work
- [ ] Merge in sets of records rather than one by one, within the
      `mdm-engineering` skill's rules (the Merge Stage record by record is a
      rule today: change it only with the operator)
- [x] Find what the 16 minutes after `processed` are (2026-10-20 07:55 ET): `bookkeeping finalize`, sampled
- [ ] Learning → skill
