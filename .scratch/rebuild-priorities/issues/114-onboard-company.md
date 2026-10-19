# Onboard SEC Company: test, acquisition proof, approval, switch-on

Priority: 114 (taken first: operator, 2026-10-19, "must onboard company no excuses"). Map: [Rebuild priorities](../map.md).

Type: task. Status: in progress (Claude, 2026-10-19). Then GLEIF and the rest, one source at a time (operator, 2026-10-19: "Can you turn on company mastering one source at a time sec, geilf, and the rest"). Blocked by: none. Takes over: ticket 02's and ticket 71's "Activate the SEC Company source" parts for a local switch-on; Grok's stopped Company proving run (#1098's handoff, 2026-10-18).

## Operator rulings

- 2026-10-19: "must onboard company no excuses".
- 2026-10-19, asked whether one bounded acquisition from data.sec.gov may run from this machine to make Company's acquisition proof: "Yes, 5 companies (Recommended)". Withdrawn by the next ruling: no SEC request is made.
- 2026-10-19: "No not acceptable can you decouple actual turning on to live data to test and turn on the pipes using already captured data". So switching on the pipes (a source version processing captured data: its test run, approval and activation) no longer needs an acquisition proof; switching on live acquisition (a run with a feed, the capture worker) still does, separately (ticket 71).
- 2026-10-19: "You have done proving runs 100s of times why do you need more runs how do you record for that make all skills understand 7 wastes and eliminate any of the waste from each skill". So Company's existing proof is recorded, not run again, and the declared writer for Company is dropped (over-production).
- 2026-10-19: "Everything must be configuration and skill driven not code new". Asked whether two generic platform changes may be made once (the decoupling; the declared writer accepting Company's inputs), after which Company, and every later source, onboards by configuration and skill steps only: "Yes, both generic (Recommended)".

## Found (2026-10-19 ET)

- `rules test` runs only a target the declared writer can build (Bookkeeping version 2, ticket 14). Company's `mastering` target is version 1; its manifest is written by `mdm prepare-clean-company` (`company_prepare.py`). What the declared form lacks for it: an input from outside the capture (the Name Census), run facts bound into contracts (the capture and catalog run ids, the census digest, the observation time), per-document context (CIK, receipt id), and a preparation that reads combined rows. That is why Grok's run stopped.
- Activation needs an acquisition proof: a real acquisition run's manifest, producer counts and checks. Three gaps:
  - Company's acquisition names producers `capture`, `sec_company` and `sec_company_filing`. The last two are the old warehouse's silver writers, and the rebuild has no such steps, so Bookkeeping refuses the run ("Configured work omits required acquisition producers").
  - Company's `capture` target copies files (`artifact.copy`), not the configured capture (`provider.capture`).
  - Bookkeeping starts a run only for an active, proven version, and a version activates only with an acquisition proof. No path makes the first acquisition proof.

## Checklist

- [ ] ~~Company's `mastering` target declared (Bookkeeping version 2)~~ dropped (2026-10-19 08:21 ET): over-production. Company already runs through `mdm prepare-clean-company` and `rules run` (`docs/company-only-acquisition.md`); the declared form is not needed to switch it on (operator, 2026-10-19, the seven wastes)
- [ ] ~~`rules test` on Company's captured documents~~ replaced: Company's last installed proof (2026-10-14, 25 minutes: 6,414 Companies and 3,052 GLEIF bindings from an empty store, the second pass changed nothing, a killed worker recovered) is recorded against today's version with the changes since, each with its own merged PR's tests, named as its evidence (`rules record-proof`); no new run
- [x] Decouple (2026-10-19 ruling): the processing authority (proven on its test run, approved on its exact digest) is checked for a version's activation, its dataset registration and a run over captured data; the acquisition authority (that plus the acquisition proof) only for a run with a feed and the capture worker; a test run of a source that declares acquisition is recorded with `rules test --version`. GoF consult; tests per case (2026-10-19 08:15 ET): `processing_authority` (`acquisition_authority.py`) beside `frozen_authority`; Bookkeeping admits a run by feed or not; Rules migration 004; `Rules.prove`/`activate` check acquisition evidence only when a proof carries it; data-onboarding SKILL.md and APPROVE.md say so. GoF consult: extract a function, no pattern (`acquisition_authority.py` changed twice since September). Tests: `tests/unit/test_processing_authority.py` (4), `test_rules_approval_postgres.py` (pipes on a test run; live acquisition still refused), `test_rules_proving_record_postgres.py` (an acquisition source records its test run); affected run 875 passed
- [ ] ~~Company's acquisition on the configured capture, the first acquisition run, 5 companies from data.sec.gov~~ deferred to ticket 71 (operator, 2026-10-19: switching on live data is decoupled from switching on the pipes); Company's stale `required_producers` (`sec_company`, `sec_company_filing`) go with it
- [ ] A local Rules Database (disposable, not the shared test instance): the version saved, its test run recorded
- [ ] The operator's approval words for the version, recorded
- [ ] Activation (`rules activate`) into the local MDM; `rules run --target mastering` on a bundle of captured companies
- [x] Slice 1 three-axis review (2026-10-19 08:21 ET): GoF "leave it" (one readability edit taken); Standards: a run with no feed could hold a capture step, an empty feed counted as none, no test through `Bookkeeping.start` (all fixed, 2 tests); Spec: stale "activation needs an acquisition proof" in COMPLETION.md and two docs (rewritten), how live data is switched on later (APPROVE.md: a new version). 188 passed
- [ ] Slice 1 PR, CI, merge
- [ ] Tickets 02, 71 and 14 updated
- [ ] Learning → skill
