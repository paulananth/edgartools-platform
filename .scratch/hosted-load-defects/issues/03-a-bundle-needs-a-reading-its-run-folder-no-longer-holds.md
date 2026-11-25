# 03: A bundle of a run fails because its run folder no longer holds a reading it needs

Status: open
Type: bug
Blocked by: none

Found 2026-11-25 in the hosted reload (2026-11-24 23:06 ET): `openfigi-answers` stopped on 1 of its 16 bundles with
"Artifact missing or unreadable" for a reading file under the first bundle's folder, while the run folder held only the
fifth bundle's folder. The other 15 bundles had finished. The second attempt finished the run (7,730 documents already
loaded) and the step completed. The same kind of missing-manifest error is in the hosted error log for other OpenFIGI and
N-PORT security runs of earlier days, so it recurs.

## Checklist

- [ ] Find what removes a bundle's folder while a later bundle of the same run still reads it (the run's cleanup, or a
      second process on the same manifest root), with a test that fails first
- [ ] Fix the cause, never the retry
- [ ] Learning → skill: `data-operations/HOSTED-LOADS.md`, "Mount every folder a run's documents live in", if the cause is a
      mount or a cleanup the loader owns
