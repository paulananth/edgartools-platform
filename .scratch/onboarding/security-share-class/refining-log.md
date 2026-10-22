# Refining log: a Security's share class (ticket 130)

Skill: refining-rules (live Security sources `sec.thirteenf.information_table`
and `sec.nport.security`). Counts only; the local copies stayed on the machine
and no request left it.

## The ruling

Operator, 2026-10-22: "Approve the rule (Recommended)": the Security carries
`share_class`, one letter, from "CL", "CLASS" or "CLS" then one letter in the
filed titles; filers that disagree give none and a quality check lists the
Security; no RDM code set; a Form 4 title is read the same way (ticket 24).
Research: `.scratch/security-mastering/research/01-share-class-standards.md`.

## What changed

- 13F: a table of each title's class (titles naming none left out), a
  reduction of the classes per CUSIP, the class joined only when exactly one
  is filed, every letter kept for the quality check. New `quality.yaml`
  (`sec-thirteenf-security-quality-v1`): `share_class_one_letter`, flag only.
- N-PORT: the same from equity holdings (asset category EC) only, by CUSIP,
  by ISIN, and for ISIN-only holdings folded into a CUSIP (the CUSIP's own
  letter first, as for the title). Quality `sec-nport-security-quality-v2`.
- MAPPING.xlsx for both sources and `security.xlsx` regenerated.

## Evidence

- `oracle.py` over the local copies (`oracle-counts.json`): 13F 2,953,581
  rows, 29,942 CUSIPs, 2,896 with a letter, 5 with two; N-PORT 2026q2 equity
  24,946 CUSIPs, 1,402 with a letter, 5 with two; N-PORT non-equity 15,946
  CUSIPs the recipe would letter (bond tranches), so equity only.
- `recipe_parity.py`: the committed recipe, run by the source engine over all
  163,731 distinct local titles (`titles_dump.py`), equals the oracle on
  every one; 6,656 name a class.
- `tests/integration/test_security_share_class.py`: both chains on invented
  holdings: one letter kept, a bare title none, two letters none and flagged,
  "CL" alone and "CLASS AB" none, an N-PORT bond tranche none.

## Known limit

Across sources the first-ranked source wins the field (N-PORT before 13F),
as for the title; the merge has no "agree or none" field rule. 777 CUSIPs
carry a letter in both sources; they disagree on 1.
