# 28 — Add conditional-fetch validators and not-modified linking

**What to build:** Let a re-poll of an already-captured logical source key
send `If-None-Match`/`If-Modified-Since` validators from the prior verified
capture and, on a `304`, link the new decision to that prior evidence
without a new SEC download, a new Bronze write, or double-counting the
capture as distinct new evidence.

**Blocked by:** 17 — Make Bronze capture retry-safe and recoverable

**Status:** ready-for-agent

## Why this is its own ticket, not part of Ticket 17

Surfaced while resolving Ticket 17. Three structural facts, verified against
the live code, mean this genuinely cannot land as a small addition to an
existing call path -- it needs a caller that does not exist yet:

1. `AcquisitionLedger.claim_fetch`'s `claimable` set is `{READY, FAILED}`
   plus an expired `LEASED` -- `CAPTURED` is deliberately excluded (a
   finalized decision is done). A conditional re-poll therefore cannot
   reuse the original decision; it needs a **new** decision for the same
   `logical_source_key`.
2. That new decision has nowhere to get the validators from today. The
   `uq_source_fetch_work_active_key` partial index excludes `CAPTURED`, so a
   new work row for the same logical key *is* creatable -- but nothing in
   `AcquisitionLedger` exposes "the ETag/Last-Modified from the latest
   verified capture for this logical key," only per-`decision_id` reads
   (`source_change_status`, and Ticket 17's new
   `latest_transition_reason`). This needs a new ledger read API, not just
   new columns.
3. Nothing produces the cause that would trigger a re-poll in the first
   place: `DecisionCause.DUE_POLICY` exists as an enum member but has zero
   callers anywhere in the codebase (confirmed via grep). Shipping
   conditional-GET support with no live call path would be dead code.

Ticket 17's own bullet 2 ("`304` and same-bytes/same-producer observations
link to prior verified evidence") is only half-closed by that ticket: the
same-bytes/same-producer half is already satisfied by Ticket 15's
content-addressed Bronze writes (identical bytes reuse one object regardless
of how they were re-observed -- already tested). The `304` half is what this
ticket adds.

- [ ] `sec_client.py` gains conditional-GET support (an `If-None-Match`/
  `If-Modified-Since` request path) that distinguishes a `304` response from
  a `200` with bytes, without changing the existing `download_sec_bytes`
  call signature any existing caller relies on.
- [ ] `AcquisitionLedger` exposes a read of the latest verified capture's
  validators (ETag/Last-Modified) and artifact reference for a given
  `(source_family, logical_source_key)`, independent of any specific
  `decision_id`.
- [ ] A due re-poll (via `DecisionCause.DUE_POLICY`, or whatever concrete
  poll-scheduling mechanism this ticket's own grilling settles on) creates a
  new Fetch Decision for the same logical key, sends the stored validators,
  and on `304` finalizes CAPTURED referencing the *prior* artifact reference
  -- no new Bronze write, no new raw evidence hash.
- [ ] A `200` response (content actually changed) proceeds through the
  normal Ticket 15 capture path with a new content-addressed write.
- [ ] An end-to-end test proves a `304` re-poll performs zero Bronze writes
  and that the new decision's `captured_artifact_reference` matches the
  prior decision's, while a changed-content re-poll produces a genuinely new
  artifact.
