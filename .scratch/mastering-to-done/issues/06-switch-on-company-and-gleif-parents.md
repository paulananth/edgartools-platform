# Switch on Company and the GLEIF parents

Type: grilling (HITL)
Status: in progress (Claude, branch `claude/mastering-06-switch-on`)
Blocked by: 02, 04, 05, 13

## Question

Where and in what order do the approved versions get switched on (`rules activate`)?

- **The target:** a fresh local Clean MDM database to create and migrate (`mdm migrate`). Which port and container name, and is it kept as the operator's store?
- **The order:** Company first, then the GLEIF accounting parents. Person comes later, in ticket 12.
- **Proof before each switch-on:** the run on captured bronze that the operator reads first.

## Carried in

- Review finding 5, from ticket 05: build the GLEIF batches by bytes, under the 16 MiB save cap. Measure a 1,000-record batch after the #772 fix first; it was 43 MB in ticket 27.
- D5, from ticket 02: whether link ends stop the closure, measured at full GLEIF scale.
- Ticket 04: prove `rules run --target mdm` end to end on this run.

## Checklist

Operator, 2026-10-02: "agreed" (to fresh local Rules and MDM stores kept as the operator's, re-proving, then re-approval).

- [x] **The lost Rules Database.** At 15:42:42 ET a Docker prune (not Claude's) deleted every Colima image and volume, including `rules-local-person-feed-1` and its approvals. No backup existed; the rules files are in git and each approval's digest and words are in the tickets. Evidence: `docker events` (volume destroy, then volume prune at 15:42:42 and 15:43:10 ET). 2026-10-02 16:15 ET
- [x] **The target** (decided, per "agreed"):
  - `edgartools-rules-local` on 127.0.0.1:5433 and `edgartools-mdm-local` on 127.0.0.1:5434, both postgres:16-alpine with `--restart unless-stopped`;
  - named volumes `edgartools-rules-local-data` and `edgartools-mdm-local-data`, labelled `edgartools.keep=operator`;
  - passwords in `~/.local/share/edgartools/local-stores.env` (mode 600), never printed;
  - Rules: `rules init` (001–003), roles `rules_agent`, `operator`, and `rules_approver` granted to `operator`. MDM: `mdm migrate` (001–004), runtime role `application`;
  - a `pg_dump` of both stores after each step, in `~/.local/share/edgartools/db-backups-20261002/` (first at 16:15 ET).

  2026-10-02 16:15 ET
- [x] **The versions saved from git, digests compared:**
  - merge `platform-2026-10-01.gleif-parents` 4c9d1cee…26f8: same as approved;
  - source `gleif-2026-10-01.parent-links` fecfcbf9…9347: same as approved;
  - source `sec.submissions.company-2026-10-02.switch-on` fc643704…40d1: no approval of this digest is recorded anywhere. A first save under a trial's label (`…2026-09-30.postcode-flag`) stays as an unused draft, since Rules history is append-only.

  2026-10-02 16:15 ET
- [x] **The order holds:** the GLEIF-parents merge version carries the Person kind, but its two Person rules read only `sec.submissions.person.v1`. Nothing reads Person until that source is switched on (ticket 12). 2026-10-02 16:15 ET
- [x] Re-run the GLEIF-parents proving run (06a2) on main after #793 and #796, new counts beside the old: every count is the same (6,414 Companies, 3,052 with CIK and LEI, 9,466 matching decisions, 282 parent links: 86 direct, 110 ultimate, 86 calculated ultimate; 664 binding reviews; 312 set aside; second pass changed nothing; policy 4c9d1cee) except one: the 72 open "unresolved endpoint" link reviews are gone, as #793 intends. 17 min 41 s. Evidence: `report-06a2.json` beside `report-06a2-2026-10-01.json`, log `proving-06-rerun.log`. 2026-10-02 16:33 ET
- [x] The 72 are now waiting links: the script gained a `waiting_links` count and the run repeated on main 125432d7: `waiting_links: {unresolved_endpoint: 72}`, every other count unchanged (only fresh entity ids differ). 19 min 30 s. Evidence: `report-06a2.json` (sha256 eb50260e…6fbe), `proving-06-rerun2.log`. 2026-10-02 16:52 ET
- [x] Finding 5: a save of 200 GLEIF records is at most 3.24 MB (second pass, 87 reviews), and a save of 200 links at most 2.44 MB, a fifth of the 16 MiB cap. Reviews' copied lists are 0.01 MB per save after #772. 1,000 records would come to about 16 MB, so the run keeps saves of 200; no code builds GLEIF batches yet (ticket 05), so byte sizing goes to whatever builds them for `rules run` (ticket 04). Evidence: the `{"save": …}` lines in `proving-06-rerun.log`, byte-for-byte equal to the 2026-10-01 log. 2026-10-02 16:33 ET
- [x] D5 at the cohort's scale: link ends stop the closure. 272 links over 3,716 GLEIF and 6,414 SEC records give review lists of 0.01 MB per save, and saves do not grow from first pass to second. Save times varied between runs (GLEIF first pass 470 s then 279 s, second pass 146 s then 367 s, same bytes), so the timings are machine noise, not a signal. 2026-10-02 16:33 ET
- [ ] ~~D5 at full GLEIF scale~~ deferred: the full Golden Copy does not fit in the disk that is free (14 GiB)
- [x] Proof recorded for merge version `platform-2026-10-01.gleif-parents` (4c9d1cee…26f8): `proof-merge-gleif-parents.json` (sha256 d095fbe8…cb2d), passed; `rules pending` lists it with evidence hash 52547d16…6d46. Rules store backed up (`edgartools-rules-local-1653-proven.sql.gz`). 2026-10-02 16:53 ET
- [x] The operator approved merge version `platform-2026-10-01.gleif-parents` (4c9d1cee…26f8), evidence 52547d16…6d46. Operator, 2026-10-02: "yes". Recorded by `rules approve` (approved_at 17:09 ET). 2026-10-02 17:09 ET
- [x] Activated into `edgartools-mdm-local` (`rules activate`, `RULES_MDM_ACTIVATION_DATABASE_URL`): Rules shows it `active`, and `mdm.policy` holds policy 4c9d1cee…26f8. Both stores backed up (`edgartools-{rules,mdm}-local-1709-active.sql.gz`). 2026-10-02 17:09 ET
- [ ] ~~Activate the SEC Company source~~ blocked: activation needs an acquisition proof (manifest, producer counts, checks) from a real acquisition run. That fetches from data.sec.gov through the coupled Bookkeeping path, which `skills/bookkeeping/INDEPENDENCE.md` (#785) says not to use as a fallback. This is the operator's call.
- [ ] ~~Activate the GLEIF source~~ blocked: `rules/sources/gleif/source.yaml` declares no `acquisition`, which source activation requires
- [ ] ~~Ticket 04: prove `rules run --target mdm` end to end~~ blocked by the same Bookkeeping gap
- [ ] PR, CI green, merge on the operator's word
