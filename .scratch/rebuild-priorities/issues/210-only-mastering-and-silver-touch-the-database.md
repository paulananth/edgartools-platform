# 210: Only mastering and silver touch the database

Priority: 210. Map: [Rebuild priorities](../map.md). Opened 2026-11-11 06:41 ET (operator: "only time anything hists the database is mastering and silver. source combine must be done locally" and "why do we need verifier at all there is nothing to verify we are extracting and mergying").

Type: task, charted with wayfinder. Status: open. Blocked by: none.

## Destination

A load reads and combines captured files locally and writes files with receipts. The database is reached only by mastering (Source Stage and merge) and silver (land and derive). Read and combine have no claim, lease, heartbeat or verifier. Those steps are proved by the content hash and the Change Journal.

## Why

On the hosted store each control call costs about 2 s (a first connection 0.9 s, the frozen run 0.6 s) and each query about 43 ms, against 0.2 ms locally. A run of 553 read units takes hours in claims and checks. A combine claim composes the receipt of every unit it reads, and took over 170 s, longer than its 120 s lease: the run failed with "Stale lease" before the work started.

## Parts

- [ ] Design: a step marked local runs in the loader's own process, writes its output files and receipt, and records no database row; the database run starts at the Source Stage step with the receipts as its inputs. Consult `/gof-refactor-reviewer` first.
- [ ] Rule: the bookkeeping skill names which operations are verified (destination writers: mastering merge, silver land and derive) and which are not (source read, source combine). Verified by the skill lint.
- [ ] Build it, with a test that fails before the change (a read and combine of N units issue no database call).
- [ ] Prove on `local-staging`: a small load gives the same counts as before.
- [ ] Hosted OpenFIGI answers load finishes inside the operator's 1 to 2 hour window.
- [ ] ~~Claim speed fix (one store query per step in a composed input)~~ deferred: only needed if a verified step still composes many units; decide after the design.
- [ ] Learning → skill: the bookkeeping skill line that names the unverified operations.
