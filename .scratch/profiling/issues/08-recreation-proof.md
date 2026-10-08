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
- [ ] ~~Baseline: today's rules mastered on the cohort on a disposable PG16 (Company, Person, GLEIF Level 1 with successors, GLEIF relationships, the pinned RDM code set; second pass changes nothing)~~ deferred until Codex's old-parser retirement merges: mastering starts from SEC Company records (a GLEIF record binds only through one, so GLEIF alone masters nothing), and today's SEC reading into MDM is what Codex is replacing: the landing path of the earlier Proving Runs is deleted, the configured path still waits on census, catalog and pagination, and open PR #858 replaces the SEC field extraction (trials/proof/README.md)
- [x] Rulings file: `trials/proof/rulings.py` → `rulings.jsonl`, 479 rulings from every ticket under `.scratch/`, each list item, table row or paragraph kept whole and verbatim with its ticket, line and section; a ruling written in no ticket is not there, and the agent records the question as "unanswered, would ask the operator" 2026-10-07 21:01 ET
- [x] Sandbox: `trials/proof/sandbox.sh <commit> <folder>`: the repo at one commit without rules, .scratch, .planning, tests, research, qualification scripts, internal docs, CLAUDE.md and AGENTS.md; the slice and rulings copied in; empty EDGAR_RULES_ROOT; network blocked by proxy; tried at f9c0561f (135 MB); `still-named.txt` lists the 27 files that still name a feed (skills' Examples, specs, and platform code with feed logic: company_source, cascade, matching, names), for DIFF.md to explain 2026-10-07 21:01 ET
- [ ] ~~Cold agent: time estimated and stated before launch; regenerates the rules with the skills into the sandbox~~ deferred until Codex's retirement merges: it writes SEC source rules in the shape Codex is still settling
- [ ] Rulings file replayed in sandbox
- [ ] Sandbox rules mastered on the cohort with the same script
- [ ] The baseline and the sandbox mastering read GLEIF through the configured Rust reading (`rules/sources/gleif/level1-json.yaml` with the cohort's LEIs as `approved_scope`, selected inside the engine), the platform's own path; the slice used a direct stream (the production verifier hands all 3.4 million records to Python: about 10 times slower, operator asked 2026-10-07 20:46 ET "why are you not using the rust parser")
- [ ] DIFF.md: rules field by field, mastering (counts, bindings digest, reviews, relationship periods), RDM code set hash; every line matched or explained; feeds not covered listed; 13F rows wait for 06
- [ ] Review, PR, CI, merge on the operator's word
- [ ] Operator accepts — program ends
