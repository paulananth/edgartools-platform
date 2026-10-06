# Quality trial

contoso: profiled with the current code; findings approved for this trial only.

| Part | Defects | Became checks or fixes | Counts equal | Planted fire | New code |
|---|---|---|---|---|---|
| customer | 6 | 5 | 5 of 5 | 5 of 5 | hierarchy_invalid |
| date | 10 | 10 | 10 of 10 | 10 of 10 | - |
| orderrows | 1 | 1 | 1 of 1 | 1 of 1 | - |
| orders | 1 | 1 | 1 of 1 | 1 of 1 | - |
| product | 6 | 6 | 6 of 6 | 6 of 6 | - |
| sales | 2 | 2 | 2 of 2 | 2 of 2 | - |
| store | 3 | 3 | 3 of 3 | 3 of 3 | - |

28 of 29 defects became engine checks or fixes; the rest are new code, each with what its check would test (QUALITY.md per part). A code-list guard counts 0 on its own delivery by design: its planted record proves it fires.

Invalid hierarchy rows marked: 4; 4 with an evidence-backed fix, 0 for a steward; 0 without either.

**Every check loads, counts what profiling counted, and fires.**
