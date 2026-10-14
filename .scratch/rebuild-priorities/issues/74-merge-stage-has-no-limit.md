# The Merge Stage has no limit

Priority: 74, tier 1, in flight (raised by the operator, 2026-10-14). Map: [Rebuild priorities](../map.md).

Type: task (code). Status: claimed (Claude, 2026-10-14 ET, branch `claude/merge-no-limit`). Blocked by: none. Blocks: ticket 01's ownership Proving Run.

## Why

The ownership Proving Run (ticket 01, 2026-10-13 20:55-21:14 ET) stopped in its first pass: "Affected closure exceeds bounded replay budget". The Merge Stage replays a batch with everything it is connected to, and its closure follows links both ways: an owner's record pulls in its issuer, the issuer every other owner that links to it. The cohort's insider network (8,272 owner records, 1,706 issuers and their decisions) is one group, past the 10,000 cap. The same cap made Form ADV keep custodian links out of MDM.

Operator, 2026-10-14: "Fix the Merge Stage (Recommended)" (a link pulls in only its target's own records unless the batch changes the target's identity), then "merge stage should have no limit".

## What "no limit" covers

- **Removed: every refusal by size.** The closure cap (10,000 records, decisions and identities), the projection retirement and projection caps, the assessment history cap, the save request's 16 MiB cap and the match proposal's stored and sent byte caps, in Python (`merge.py`, `limits.py`) and in SQL (a new migration replacing `write_batch`, `preview_batch` and `record_match_proposal` without them).
- **Kept: how the input is cut.** `mdm.prepare` still cuts a run's records into batches of at most 1,000 records and 1 MiB (`limits.batches`); that divides the work and refuses nothing, and the batch's own assertion, decision and deferred counts stay checked against it.
- **Then, if the replay is slow:** narrow the closure (the operator's first answer) as speed work.

## Checklist

- [ ] GoF consult on `merge.py`'s closure and the limits
- [ ] Remove the size refusals in Python; the closure and projection queries unbounded
- [ ] A migration replacing the SQL functions without the byte caps; `test_clean_limits.py` states what stays
- [ ] Tests: a closure over the old cap applies; a request over 16 MiB saves
- [ ] The ownership Proving Run reruns: both passes, time measured
- [ ] Three-axis review
- [ ] The full installed proof (a Merge Stage change)
- [ ] PR, CI green, merge on the operator's word
