# 170: How many workers, and the worker architecture

Priority: 170. Map: [Rebuild priorities](../map.md). Opened 2026-11-02 09:12 ET (operator, 2026-11-02: "Park a question or a ticket how many workers and its architecture").

Type: question (parked; nothing is worked until the operator unparks it). Status: closed (2026-11-11 15:02 ET, operator: "Close all tickets"): its open parts are ticket 212's. Blocked by: none. Related: [169](169-company-financials-run-through-bookkeeping-and-the-change-journal.md) adds the first silver worker.

## Question

How many workers should a load run, and what is the architecture around them (processes, logins, leases, resource sizing, where verifiers run, how the number changes between a laptop, the shared local server and the hosted target)?

## What is already known (read from the skills, not measured)

- A worker is a separate process that pulls task envelopes from Bookkeeping's commands, renews its lease while it works and reports a candidate. A verifier is a separate run that reads the destination back and checks. Neither receives Bookkeeping's engine or database (`edgar_warehouse/workers/__init__.py`).
- A step's `operation` names the worker profile; a new profile is one module plus an entry in `PROFILES`.
- The load command takes `--workers <readers>`, `--bundles <runs at once>` and `--minutes <window>` (`skills/data-operations/SKILL.md`). Workers and verifiers connect as their own restricted logins.
- `data-operations` says "`silver land` is the manual write until that worker exists": no silver worker yet (ticket 169).

## Parts (nothing started)

- [ ] ~~Measure: what limits a load today (reader count, Postgres connections, the Merge Stage, memory); one measured run per limit, not a sweep~~ deferred to 212: the operator closed all tickets (2026-11-11 15:02 ET: "Close all tickets consolidate remaining issues into new ticket by priority and go-live").
- [ ] ~~Decide the default worker counts per operation (`source.read`, `mdm.prepare`, `mdm.merge`, `silver.land`) and whether they are rules, flags or sizing from the measured time~~ deferred to 212: the operator closed all tickets (2026-11-11 15:02 ET: "Close all tickets consolidate remaining issues into new ticket by priority and go-live").
- [ ] ~~Decide where each kind runs (local processes, containers, the hosted target) and how leases and logins scale with the count~~ deferred to 212: the operator closed all tickets (2026-11-11 15:02 ET: "Close all tickets consolidate remaining issues into new ticket by priority and go-live").
- [ ] ~~Write the architecture in one page and the numbers in the `data-operations` skill~~ deferred to 212: the operator closed all tickets (2026-11-11 15:02 ET: "Close all tickets consolidate remaining issues into new ticket by priority and go-live").
- [ ] ~~Learning → skill: `data-operations` and `bookkeeping` name the worker counts and the sizing rule~~ deferred to 212: the operator closed all tickets (2026-11-11 15:02 ET: "Close all tickets consolidate remaining issues into new ticket by priority and go-live").
