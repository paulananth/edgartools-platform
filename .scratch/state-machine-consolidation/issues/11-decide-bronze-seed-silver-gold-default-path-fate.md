Type: grilling
Status: claimed

**Spawned by:** [Ticket 09 — Retire superseded document-loading machines](09-retire-superseded-document-loading-machines.md)'s deferral (2026-09-05): `bronze_seed_silver_gold`'s default path was confirmed to still be install.sh's live, documented "canonical one-click path for cold-starting or recovering an environment's silver/MDM/gold from a bronze snapshot" (`{"batch_size": 100, "release_mode": false}`), directly contradicting the ticket's original confirmed-unused premise for that one machine. The user chose to defer rather than retire-and-break or redesign `install.sh` in the same pass.

## Question

What is `bronze_seed_silver_gold`'s default path's actual fate — retire it (and redesign `install.sh`'s cold-start/recovery path onto something else), keep it as-is permanently, or fold it into a different consolidated shape?

Context to bring into the conversation:

- `install.sh` triggers this machine directly by name for cold-start/recovery — any retirement decision has to say what replaces that call, not just delete it.
- [Ticket 07](07-collapse-mdm-tail-to-a-single-deployed-machine.md)'s original design for this machine (rewiring its tail onto the new single deployed MDM machine) was paused and is now considered moot, per Ticket 08's resolution: `mdm reconcile-backstop` already independently serves the one capability (unbounded full-universe mastering) that design existed to preserve. Confirm this is still true before assuming it settles the question.
- The machine's separate "strict release mode" branch (`{"release_mode": true}`) is explicitly out of scope here — Ticket 07 already decided it stays untouched, not reopened by this ticket.
- Live execution history for the default path (last checked as part of Ticket 09) should be re-verified before deciding — confirm via `aws stepfunctions list-executions` whether `install.sh`'s cold-start path has actually been exercised recently, not just documented as callable.

Use `/grilling` and `/domain-modeling` per this map's convention — this is a real product decision (whether to keep, retire, or redesign a documented operational recovery path), not mechanical.

## Answer

_(pending)_
