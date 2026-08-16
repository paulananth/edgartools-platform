# Documents migration inventory

Type: research
Status: resolved
Blocked by: 02

## Question

What is inside `~/Documents/Existing files/Macintosh HD - Data` (~21 GB) — safe to delete leftover, or keep?

## Answer

This is a **full old macOS volume dump** (dated ~2021–2022), not normal Documents content:

| Path under `Macintosh HD - Data` | Size |
|----------------------------------|-----:|
| Users | **13 GB** |
| → Users/aneenaananth | **12 GB** |
| → → Library | **9.9 GB** |
| → → Pictures | **2.4 GB** |
| → → Downloads | 78 MB |
| private | 2.9 GB |
| System | 2.1 GB |
| Library | 2.0 GB |
| Applications | 148 KB |

Sibling folder `DiskDrill` exists under `Existing files`. Structure is a classic **disk-recovery / migration residual**.

**Personal data still inside that might matter:** Pictures (~2.4 GB), Downloads (~78 MB), Desktop (~46 MB), old Library.

**Recommendation:** If current `~/Pictures` and photos are intact elsewhere (iCloud/Photos library), this entire tree is a strong delete candidate for **~21 GB**. Confirm before delete.
