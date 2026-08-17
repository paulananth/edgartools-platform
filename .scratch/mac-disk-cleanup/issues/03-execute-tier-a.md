# Execute Tier A safe cleanup

Type: task
Status: resolved
Blocked by: 02

## Question

Run Tier A reclaim: Docker stopped container, gstack.bak, brew cleanup, playwright/homebrew/colima caches, Claude Desktop caches, Trash.

## Answer

Executed 2026-08-07. Free space **5.5 GB → 8.7–8.8 GB** (~**+3.2–3.3 GB**).

| Action | Result |
|--------|--------|
| `docker rm oom-repro-check` | Removed (host reclaim 0B — space likely still inside Colima VM disk until compact) |
| Delete `~/.claude/skills/gstack.bak` | **−1.1 GB** |
| `brew cleanup -s` | **−397 MB** (also autoremoved `ripgrep` — **reinstalled**) |
| Remove ms-playwright cache | **−533 MB** |
| Remove Homebrew + colima Library caches | **−453 MB + −342 MB** |
| Claude Desktop Cache + Code Cache | **−327 MB + −110 MB** |
| Trash | Empty / nothing material |

**Not done in Tier A:** Docker image prune, Colima shrink, Documents delete.
