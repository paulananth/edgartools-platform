# Switch on Person feed 1 with its links

Priority: 11, tier 2, the recreation proof. Map: [Rebuild priorities](../map.md). Moved from `.scratch/mastering-to-done/issues/12-switch-on-person-with-its-links.md` on 2026-10-13; a Blocked by list of numbers now uses this map's numbers (or names the old effort); free text keeps the old effort's numbers.

Type: task, then approval
Status: done (2026-10-14 16:58 ET): Person feed 1 and its links proved together; source activation moved to ticket 71
Blocked by: mastering-to-done 03, 02, mastering-to-done 10, mastering-to-done 11, 10

## Question

Switch on Person feed 1 together with its first relationship feed: Forms 3/4/5 (platform validation 06, steps 3–4). The operator ruled that Person is not switched on without its relationship rules.

- **Proof first:** a proof run on captured bronze, with counts and examples shown to the operator.
- **Approvals:** the operator approves the exact versions.
- **Activate:** `rules activate` in the order from ticket 06.

## Checklist

- [x] Order (operator, 2026-10-14 13:30 ET, "10, then 11; 20 later (Recommended)"): ticket 10's quality checks first, then this ticket's proof and switch-on; the catalog (ticket 20) no longer blocks this ticket and follows after 2026-10-14 13:51 ET
- [x] Its first relationship feed, Forms 3/4/5, is switched on: #964 (`ade7139d`), the ownership rules with their director, officer and ten-percent-owner links 2026-10-14 13:51 ET
- [x] Ticket 10's checks merged: #967 (`bd778ee7`); its run report checks (part 2) are reported only and do not gate this ticket 2026-10-14 15:06 ET
- [x] The switch-on proof, 2026-10-14 15:08–15:54 ET (45.8 min; `.scratch/onboarding/sec.submissions.person/switch_on_proof.py`, report local in `proving/person-switch-on/`, counts only): on main's merge rules (policy `ccd68eb5…`), one store took the 1,706 cm27 Companies the local filings name as issuers, all 76,230 submissions documents (Person feed 1) and the 8,723 filings' owners. People 31,326: 26,506 from submissions only, 4,591 from both feeds, 229 from ownership only; 0 CIKs on two people, 0 CIKs both a Person and a Company; links: director 2,477, officer 2,796, ten-percent owner 161; set aside: 11,095 deferred and 34,038 entity undetermined (submissions), 361 and 680 (owners); the second pass changed nothing; slowest batch 22.0 s of 316 2026-10-14 16:01 ET
- [x] The 4 filers the Person rule calls people and Company's cohort read are individual 13F filers (entity type `other`, no SIC or EIN); the Company rule defers all 4 (step 11), so none is a Company; the proof's 0 CIKs both a Person and a Company confirms it 2026-10-14 16:01 ET
- [x] The versions: every rule in main's policy is already approved: Person feed 1's classification and `person-cik` (2026-10-01, "Approved"), the ownership rules (2026-10-14, "Approve both (Recommended)"), ticket 10's checks (#967, "Merge when ready"); nothing new to approve 2026-10-14 16:01 ET
- [ ] ~~Source activation of `sec.submissions.person`~~ moved to ticket 71: source activation needs an acquisition proof from a real acquisition run, as for SEC Company and GLEIF (operator, 2026-10-14: "Move to ticket 71 (Recommended)")
- [x] PR, CI, merge on the operator's word: #969, CI green (six checks), operator: "Merge when ready"; merged as `4a85313e` 2026-10-14 16:58 ET
