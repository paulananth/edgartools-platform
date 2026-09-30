# Proving Run of the Company policy with both name rules on

Type: task
Status: done, in review (Claude, branch `claude/company-mastering-27-proving-run`)
Blocked by: nothing (tickets 25 and 26 merged)
Blocks: the operator's approval of the final Company policy fingerprint

## Operator rulings

- "i want to complete company master", option **A** (2026-09-29): the
  Proving Run on real pinned data with the name rules on, then the operator
  approves the final policy fingerprint.
- "yes" (2026-09-29) to building one Name Census over the whole SEC
  population and the full GLEIF Golden Copy first (ticket 26).
- Asked, with the result below in plain words, "Do you approve policy
  `75bd2b67…33dbe` as the Company master's policy, on this Proving Run?":
  **"yes"** (recorded 2026-09-30 06:11 ET). The approval covers
  `75bd2b6744c075750c5f86632aa7e9fd504be03a648f91a1b0f3ab8c51e33dbe`: the
  SEC Company classification rule, the CIK matching rule and both name
  matching rules. It activates nothing new.

## Inputs (all local, zero requests to sec.gov)

- SEC: all 76,230 filers' submissions documents copied from prod bronze
  (reads only) to
  `~/.local/share/edgartools/clean-mdm/captures/sec.submissions.company/all-76230/`,
  each with its sha256 in `receipts.jsonl`, plus the ticker catalog
  `836140c5…`.
- GLEIF: the Golden Copy of 2026-09-11 16:00, LEI2 `1b6cd9cd…a36a6a`.
- Policy: `company_source.POLICY`, `75bd2b67…33dbe` (both name rules on).

## Checklist

- [x] Copy all 76,230 SEC documents (2026-09-29, 22:08 ET; 1.44 GB).
- [x] Cut the captures: ticket 05's seven cohort chunks first (6,414
      Companies, 586 controls), then the rest by CIK in chunks of 1,000; the
      last nine are one capture of 8,230 (see Findings). 69 captures,
      `chunks.json`.
- [x] Land every capture offline (22:26 ET): 43,338 filers land as
      Companies; the other 32,892 read as individuals and land no Company
      row, so the census counts 43,338 SEC names. `27-land.py`: `bootstrap-batch` is
      retired from the CLI (#738), so this calls the pieces it used: the
      parser `SilverLandingStore.stage_submission` and the landing writer
      `write_landing_export`, pagination off as in ticket 05. Tickers:
      `27-land-tickers.py`.
- [x] One Name Census over all 69 captures and the Golden Copy, then a
      bundle for each cohort capture (`27-census-and-bundles.sh`,
      `mdm name-census`, `mdm prepare-clean-company`). Census 22:28–22:43 ET
      (sha256 `84522f67…`); 6,726 records prepared, as in ticket 05.
- [x] Merge on a disposable PostgreSQL 16 (`27_proving_run.py`): the seven
      SEC bundles, then the GLEIF records the census names for a cohort
      name, then everything again; the second pass must change nothing.
      Passed 23:26 ET (25 minutes). GLEIF batches are 200 records: a batch
      request is capped at 16 MiB and 1,000 GLEIF records came to 43 MB.
- [x] Report in plain words: Companies with a CIK and an LEI, by rule;
      waiting and review; Apple, Microsoft, Shell and ASML.
- [x] The operator approves the final policy fingerprint.

## Result (`research/27/report.json`)

- 6,414 Companies, one per SEC Company in the cohort; no CIK on two
  Companies, no Company with two CIKs or two LEIs.
- **3,052 Companies hold their CIK and their LEI** (48%): 2,861 by
  name and state of incorporation, 191 by name and postcode.
- 3,755 GLEIF records carry a name the census gives a cohort Company; 39 are
  set aside as not a Company (`unsupported_identity_kind`); of the other
  3,716, 3,052 joined and 664 wait for review (`binding_required`).
- 312 SEC records wait in classification (the controls and filers the
  classification rule does not call a Company).
- Apple (`HWUPKR0MPOU8FGXBT394`), Microsoft (`INR2EJN1ERAN0W5ZP974`), Shell
  (`21380068P1DRHMJ8KU70`) and ASML (`724500Y6DUVHQD6OXN27`) each end as one
  Company with their CIK and LEI.
- The second pass changed nothing.

## Findings

- **The census refuses a capture with no former names.** The landing writer
  skips an empty table by design (`write_landing_export`), but
  `census_filers` requires a `sec_company_former_name` member. Four captures
  of the newest filers (CIK order, chunks 70, 72, 73, 77) had none. Worked
  around here by one larger capture; the reader should treat a missing
  former-name member as none (follow-up ticket).

## What this run does not establish

- GLEIF records enter through `gleif_source.record_evidence` and
  `MergeStage.apply`, not the native consumer, which needs a Change Journal
  publication proof.
- The SEC and GLEIF readings are the repo's (ticket 18), registered with the
  test Rules authority, not yet approved in the Rules Database.
- The attempt journal is MDM's; the retired Bookkeeping root run is skipped.
