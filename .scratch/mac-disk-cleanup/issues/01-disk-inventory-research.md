# Disk inventory research

Type: research
Status: resolved
Blocked by:

## Question

Where is the disk space going — caches, temp, duplicates, Docker/Colima, large user folders?

## Answer

Measured on 2026-08-07:

| Bucket | Size |
|--------|-----:|
| Documents/Existing files/Macintosh HD - Data | ~21 GB |
| ~/.colima (actual) | ~11 GB; sparse datadisk apparent 80 GB |
| ~/projects | ~6.9 GB |
| Application Support | ~3.1 GB |
| ~/.claude | ~3.1 GB (gstack + gstack.bak = 2.2 GB) |
| ~/.grok | ~1.8 GB (sessions 1.3 GB) |
| Library/Caches | ~1.8 GB |
| ~/.bun | ~1.3 GB |
| Docker images | ~4.1 GB; stopped container ~2.89 GB reclaimable |

Free before cleanup: ~5.5–6.6 GB on 113 GB disk (Data ~94% full).
