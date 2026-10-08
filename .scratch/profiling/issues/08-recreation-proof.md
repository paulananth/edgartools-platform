# 08 Recreation proof

Type: task. Phase: B. Blocked by: all above. Map: [map](../map.md). Plan: [plan](../plan.md).

## Ruling (operator, 2026-10-07)

Only SEC submissions, the GLEIF Golden Copy and 999 13F information tables are
on this machine; every other feed is only in production bronze, which the plan
says profiling never reads. The operator: "Local feeds only (Recommended)": the
cohort is fixed from local feeds; the proof covers those and the 13F tables on
hand, and DIFF.md lists every other feed as not covered. No production read.

## Checklist

- [x] Cohort list (500 entities, 2 years) in the repo, with size and time (`.scratch/profiling/trials/cohort/`: `cohort.json`, `select.py`, README with the strata, size and time): 4 named, 171 bound to GLEIF, 75 held for a steward (all 8 reasons), 75 with no GLEIF record, 75 investment, 100 other filers; 222 with an LEI; 46 MB of SEC submissions 2026-10-07 19:57 ET
- [x] Scope note: plan decision 29 regenerates MDM, RDM and relationships; only the 13F rows (transaction data, silver) need ticket 06, so DIFF.md says 13F rows wait for 06 (an earlier report said all of 08 waited for 06: wrong). Checked against the code 2026-10-07 20:20 ET: the baseline and the cold agent wait for Codex instead (next two parts)
- [x] Slice the cohort's inputs into a local work folder (`trials/proof/slice.py`, [SLICE.md](../trials/proof/SLICE.md)): 500 SEC submissions documents and the ticker catalog (46 MB), 2,545 GLEIF Level 1, 2,892 relationship and 2,751 reporting exception records (8 MB), 16 13F tables of 6 cohort filers (72 MB); every file's sha256 in SLICE.json; 16 minutes 2026-10-07 21:01 ET
- [ ] ~~Baseline: today's rules mastered on the cohort on a disposable PG16 (Company, Person, GLEIF Level 1 with successors, GLEIF relationships, the pinned RDM code set; second pass changes nothing)~~ deferred to Codex's old-parser retirement (`.planning/workstreams/sec-configured-fields/TICKET.md`, open item "retire Company preparation/census/provenance"): mastering starts from SEC Company records (GLEIF alone binds nothing), and today's Company input is the Company preparation that item retires; a baseline is possible today but would measure a path about to be removed (trials/proof/README.md)
- [x] Rulings file: `trials/proof/rulings.py` → `rulings.jsonl`, 358 rulings (356 when first made; the handoff file added 2) from every ticket and map under `.scratch/` (not trial logs or research notes), each list item, table row or paragraph kept whole and verbatim with its ticket, line and section (verified: no truncation in the code; the 04c succession ruling, the local-feeds ruling and the durable-key ruling are each found); a ruling written in no ticket is not there, and the agent records the question as "unanswered, would ask the operator" 2026-10-07 21:01 ET
- [x] Sandbox: `trials/proof/sandbox.sh <commit> <folder>`: the repo at one commit without rules, .scratch, .planning, tests, research, qualification scripts, internal docs, CLAUDE.md and AGENTS.md; the slice and rulings copied in; empty EDGAR_RULES_ROOT; network blocked by proxy; tried at f9c0561f (135 MB); `still-named.txt` lists the 27 files that still name a feed (skills' Examples, specs, and platform code with feed logic: company_source, cascade, matching, names), for DIFF.md to explain 2026-10-07 21:01 ET
- [ ] ~~Cold agent regenerates into sandbox stores (time estimated and stated before launch; the rules regenerated with the skills)~~ deferred to Codex's old-parser retirement (same ticket): it writes SEC source rules in the shape Codex is still settling; before launch, close the sandbox's limits (README: not a jail)
- [x] Rulings file replayed in sandbox: `.scratch/profiling/trials/proof/rulings.jsonl` (358 rulings), copied into each sandbox by `sandbox.sh`; every entry is marked `"replayed": true` and `"valid_only_in": "sandbox"`, so a replayed ruling approves nothing outside it (plan decision 29). Verified: a sandbox built at this commit holds the file byte for byte, all 358 entries so marked (handoff #860, C2) 2026-10-07 21:33 ET
- [ ] The cold agent answers its questions from the rulings file, each use recorded with the ruling's ticket and line, and each question no ruling answers recorded as "unanswered, would ask the operator": with the cold agent run (deferred above)
- [ ] Sandbox rules mastered on the cohort with the same script
- [ ] The baseline and the sandbox mastering read GLEIF through the configured Rust reading (`rules/sources/gleif/level1-json.yaml` with the cohort's LEIs as `approved_scope`, selected inside the engine), the platform's own path; the slice used a direct stream (the production verifier hands all 3.4 million records to Python: about 10 times slower, operator asked 2026-10-07 20:46 ET "why are you not using the rust parser")
- [ ] DIFF.md: every line matched or explained: rules field by field, mastering (counts, bindings digest, reviews, relationship periods), RDM code set hash; every line matched or explained; feeds not covered listed; 13F rows wait for 06
- [x] Three-axis review of the slice, rulings file and sandbox: GoF no findings; Standards (rulings cut at 1,500 characters, relative sandbox path, 13F size, deferral form, overclaiming comments) and Spec (trial logs harvested as rulings, sandbox not a jail, the wait reason partly stale, slice wider than the cohort README) all fixed or recorded 2026-10-07 21:04 ET
- [x] Operator ruling: plan decision 29 says "full local copies of today's 3 sources, plus every other captured feed sliced to one coherent cohort"; the cohort (#859) and this slice cut the 3 sources to the cohort too. Asked 2026-10-07 21:04 ET; the operator: "Cohort slice (Recommended)" (all feeds cut to the 500 entities; plan decision 29 updated) and, for the baseline, "Wait for Codex (Recommended)" (built once, on the final path) 2026-10-07 21:05 ET
- [ ] Review, PR, CI, merge on the operator's word
- [ ] Operator accepts — program ends
