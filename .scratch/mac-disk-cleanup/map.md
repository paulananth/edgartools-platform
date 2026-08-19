# Mac disk-full cleanup

Labels: wayfinder:map

## Destination

**Reached (2026-08-19).** A measured, risk-tiered cleanup path that restores usable free space on this 113 GB Mac, without deleting personal Documents data until explicitly approved — Tier A executed, Colima shrunk, Documents left as-is (user closed out rather than deleting/archiving).

## Notes

- **Side project — workstation hygiene, not repo product code.** Closed out 2026-08-19; not part of the platform's active workstreams. No further sessions should pick this up unless the user reopens it.

- Domain: local workstation hygiene (not repo product code)
- Skills: research findings already captured in session; no auto-delete of `~/Documents`
- Standing preferences (accepted Q1–Q4):
  - **Done =** Tier A executed; Documents/Colima decided separately (Q1=C)
  - **Risk =** caches + Docker container prune + `gstack.bak` (Q2=B); inventory Documents before delete
  - **Colima =** shrink to **40 GiB** after Tier A (Q3)
  - **Documents =** inventory first, then human decide (Q4)
- Machine: APFS 113 GB; Data volume was ~93–94% full with ~5.5–6.6 GB free before Tier A

## Decisions so far

- [Accepted Q1–Q4 recommendations](.) — Tier A execute; risk B; Colima→40GiB; Documents inventory-first
- [Disk inventory research](issues/01-disk-inventory-research.md) — Colima/Documents/caches dominate; ~5.5–6.6 GB free at start
- [Destination and risk tolerance](issues/02-destination-and-risk.md) — Tier A + inventory-first Documents
- [Execute Tier A safe cleanup](issues/03-execute-tier-a.md) — reclaimed ~3.2 GB; free now ~8.8 GB
- [Documents migration inventory](issues/04-documents-migration-inventory.md) — old macOS volume dump ~21 GB (2021–22); Pictures 2.4 GB is main personal slice

- [Colima disk allocation](issues/05-colima-shrink-to-40gib.md) — recreated at **20 GiB** (user revised from 40); host ~/.colima ~1.1 GB
- [Docker image prune](issues/07-docker-image-prune.md) — N/A after wipe; empty image store
- [Decide Documents migration delete](issues/06-decide-documents-delete.md) — closed without deleting/archiving; user ended the effort here

## Not yet specified

<!-- empty -- destination reached, map closed out 2026-08-19 -->

## Out of scope

- System volume / SIP paths
- Force-deleting OS update snapshots
- Blind deletion of `~/projects` repos
- Full `docker image prune -a` without tag selection (Tier B, optional later)
