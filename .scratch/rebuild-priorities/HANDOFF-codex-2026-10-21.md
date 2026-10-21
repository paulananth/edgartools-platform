# Handoff to Codex: Securities (ticket 120) and what follows

Operator, 2026-10-21 17:03 ET: "Hand this over to codex to continue". Claude stops here. Codex owns
the work below from now. The standing rules in `CLAUDE.md` and `AGENTS.md` still hold:
- one branch and worktree per ticket, off `origin/main`;
- `scripts/dev/overlap_guard.sh` before every commit;
- merge on green CI;
- counts only, never a value from the data;
- no request to a data provider without permission;
- read the clock (`TZ=America/New_York date`) before every stamp.

## Where things stand

Ticket 120 (`issues/120-switch-on-securities.md`) is merged (PRs #1118 and #1119). One part is open: the switch-on in `company-on`.

Three versions are proved and approved in `company-on`'s Rules store, under the operator's standing approval ("Approved the rules always"). **None is switched on.**

| Kind | Version | Digest | Proof file (under `~/.local/share/edgartools/clean-mdm/proving/securities-on/`) |
|---|---|---|---|
| merge rules | `platform-2026-10-20.one-security-record` | e72643e3… | `merge-one-security-record-proof.json` |
| source `sec.nport.security` | `securities-2026-10-20.one-record` | 768bcc72… | `one-record-proof.json` |
| source `openfigi` | `openfigi-2026-10-20.all-fields` | 6e08fc30… | `openfigi-all-fields-proof.json` |

The evidence is in ticket 120's checklist, in short:
- **Securities:** 413,529 Securities and 1,770 held back; no identifier on two Securities; pass 2 changed nothing.
- **OpenFIGI, one CUSIP slice joined in `sec-test`:** 49,082 of 49,082 joined Securities N-PORT made; no Security was created; 158,554 listing rows.

## Next: switch on in `company-on`, only on the operator's words

Switch-on is a decision the operator makes. Ask them first, in plain words, saying what it changes.

Order:
1. `rules activate --merge platform --version platform-2026-10-20.one-security-record`
2. `rules activate --source sec.nport.security --version securities-2026-10-20.one-record`
3. Run Securities' `mastering` target over the 2026 Q2 capture. It takes about 3 h 10 min.
   - Capture: `captures/sec.nport-datasets/2026q2`.
   - Documents: `proving/nport-on/documents.json`.
   - `--capture-run sec-nport-2026q2`, `--as-of 2026-10-19T12:00:00Z`, fact `period=2026-06-30T00:00:00+00:00`.
4. `rules activate --source openfigi --version openfigi-2026-10-20.all-fields`
5. Run OpenFIGI's `mastering_cusip` and `mastering_isin` targets.
   - Run them in slices of at most 512 files: the documents lists are `proving/securities-on/figi-id_{cusip,isin}-{1..8}.json`.
   - Capture: `captures/openfigi/2026q2-nport`; `--capture-run openfigi-2026q2-nport`.
   - Merging takes about 50 minutes a slice, about 7 hours in all.
6. Report the counts:
   - Securities;
   - held back, by reason;
   - OpenFIGI records joined;
   - listing rows;
   - identifiers on two Securities (must be 0).

How a run is submitted and driven is in `skills/data-operations/SKILL.md`, "Submit and drive one run":
- prepare, then `rules run`, then each step's parallel workers and one verifier, then `bookkeeping finalize`;
- if a deadline stops a run, drive the same run again by its id;
- never change worker code while a run is live.

Run every command under its own duty's login, from `~/.local/share/edgartools/local-tests/environments/company-on/{worker,verifier,governance}.env`. Never print a database address.

## Open tickets, in `issues/`

- **122:** the Securities run time. Bookkeeping's checks take 48 of 74 minutes. OpenFIGI's merge does about 16 records a second; merging in sets is the idea to test.
- **124:** profile fund share classes before storing them.
- **125:** make every Security and fund uniquely identifiable: SEDOL, CINS, LoanX; funds without a series; shared LEIs.
- **126:** OpenFIGI for 13F-only Securities. It needs a 13F capture, and the operator's permission before any OpenFIGI request.
- **127:** a folded ISIN-only holding's earlier filing date and its other LEI. The engine has no "earliest of".
- **119 (Codex's own, in progress):** moving the merge into Rust must carry ticket 120's changes. The list is on 119's checklist: `select_details`, MDM migrations 022–023, Bookkeeping migration 007, and the newest-capture reading.

## Stores and paths

- **`company-on`:** the operator's working store. It holds OpenFIGI's answers runs from 2026-10-19.
- **`sec-test`:** stopped. It holds the one-record test and the OpenFIGI join slice. It is disposable once `company-on` is on.
- **The `security-master` skill:** linked from `~/projects/edgartools-platform-claude-skills`, a detached checkout of main. Update it with `git -C <that> checkout --detach origin/main` after skill changes merge.
- **The Mac's keep-awake** runs until about 2026-10-21 17:25 ET. Start your own `caffeinate` for long runs, and keep the Mac on power.
