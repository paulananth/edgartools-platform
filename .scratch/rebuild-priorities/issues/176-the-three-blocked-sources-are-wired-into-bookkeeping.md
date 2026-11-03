# 176: The three blocked sources are wired into Bookkeeping before any is switched on

Priority: 176. Map: [Rebuild priorities](../map.md). Opened 2026-11-02 19:13 ET (operator, 2026-11-02: "wire bookkeeping then only we can turn on").

Type: task. Status: open, not started. Related: [172](172-the-thirteenf-securities-run-through-bookkeeping-and-the-change-journal.md) (the 13F target is the pattern), [174](174-sec-prospectus-final-prospectuses-looked-up-on-mdm-then-landed-in-silver.md) (`sec.prospectus`).

## Question

Nine sources have a Bookkeeping target in `rules/source-sequence.yaml`. Three have none and are blocked with `source_target_not_configured`: `sec.ownership`, `iapd.adv` and `sec.registration`. The operator turns sources on one at a time in the new local store (`source-by-source`), and wants every target wired first. No source is registered, approved or switched on by this ticket.

## What is known (no request)

- `sec.ownership` has its read rules (XML and SGML), its quality file and two silver specs (`insider_ownership`, `insider_position`). It needs a mastering target for the owner (a Person or a Company) and `silver.land` steps for both silver tables, after the merge, so each row finds its MDM ids.
- `iapd.adv` has its read rules (two CSV files and a combine contract) and its quality file. It needs a mastering target.
- `sec.registration` has a capture-only target (version 1) and no read rules. What its second step reads is the operator's decision (ticket 149 kept the document unread first), so it is last.

## Change Journal (operator, 2026-11-02: "also needs change journal")

Every target ends with the `journal.record` step (the 13F target's `processed`), so the Change Journal skips a file already processed with the same source, key, content hash and processing identity, and names every file again when a rule changes. Each source below is done only when a test shows both: a second pass changes nothing, and a changed rule names every file again. `sec.registration`'s capture target has no `journal.record` step today; it gets one.

## Order (recommended)

1. `sec.ownership`: its rules and silver are complete.
2. `iapd.adv`: its rules are complete; no silver.
3. `sec.registration`: waits for the operator's decision on what is read.

## Parts

- [ ] `sec.ownership`: the mastering target (read, record, prepare, merge, processed), written like the 13F target
- [ ] `sec.ownership`: the `silver.land` steps for `insider_ownership` and `insider_position`, after the merge
- [ ] `sec.ownership`: the Change Journal step ends the target; tests at plan level and through the real workers on Postgres (a second pass changes nothing; a changed rule names every file again)
- [ ] `sec.ownership`: `target: mastering` (or the silver kind the engine names) in `rules/source-sequence.yaml`, with the pinned-order tests
- [ ] `iapd.adv`: the mastering target (read, combine, record, prepare, merge, processed)
- [ ] `iapd.adv`: the Change Journal step ends the target; tests at plan level and through the real workers; `rules/source-sequence.yaml`
- [ ] `sec.registration`: the operator decides what the second step reads (the document unread, or facts)
- [ ] `sec.registration`: its target beyond capture, with the Change Journal step added after capture, tests and `rules/source-sequence.yaml`
- [ ] Learning → skill: name the skill line this ticket changed (`data-onboarding` target writing), or "none"

## Not in this ticket

Registering, testing, approving and switching on a source in the new store: each waits for the operator's words, one source at a time.
