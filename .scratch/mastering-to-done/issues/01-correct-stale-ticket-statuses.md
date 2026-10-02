# Correct stale ticket statuses

Type: task (AFK)
Status: resolved
Blocked by: none (small; any time)

## Question

Which open-looking tickets are already merged, superseded or dead? Each one's status must match git.

Candidates:
- **Rules skill:** 02–08, 10, 12 (#744), 13 (#745).
- **Company mastering:** 03, 04, 06, 09, 10, 11, 12, 16, 18, 21 (#746), 22 (#742), 23 (#749).
- **Clean MDM:** 04–07.
- **Person consumer contract:** 22 and 27.
- **Platform validation:** 03 (#767), 04 (#765) and 05a (#769), plus the map's ticket list.

For each, record merged (with the PR), superseded (by what), or still open (with the real next step). Never delete a checklist item.

## Answer

On 2026-10-02 (by 10:55 ET), 31 tickets got a corrected `Status:` line naming the PR or the ticket that replaced them. The old status is kept beneath it as `Was:`, and no checklist item was deleted. Each status was checked against `git log` on main, `gh pr list` for the ticket's branch, and the current code.

| Outcome | Tickets |
|---|---|
| Resolved | company mastering 04, 09, 11, 18, 22, 23; rules skill 02, 07, 08, 12, 13; Clean MDM 04; person consumer contract 22; platform validation 03, 04, 05a |
| Superseded | company mastering 03, 06, 10, 12, 16; Clean MDM 05 |
| Moved to this map | company mastering 21 (→ 07); rules skill 03, 10 (→ 08); rules skill 04, 06 (→ 09); rules skill 13's Person part (→ 11); person consumer contract 27 (→ 03) |
| Still open, later | rules skill 05 (silver outputs); Clean MDM 06–07 (hosted cut-over) |
