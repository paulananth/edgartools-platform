# DTCC directory discovery

Status: exploratory local-file profile; unapproved. No source or MDM activation.

Repeat investigation under the updated skills: [discovery story](../../../docs/research/dtcc-discovery-repeat-2026-10-09.md).
The original evidence below is preserved. Repeat profiling reproduces it;
the new note resolves the duplicate-row patterns and documents restrictions
found in the full DTCC terms before any automated onboarding.

## Captures and coverage

Ten anonymous HTTP GETs returned 200. Raw workbooks total 1,124,637 bytes.
Capture receipts preserve URL, landing-page hash, UTC acquisition timestamp,
HTTP status, byte count and SHA-256. Raw workbooks stay outside Git at
`/private/tmp/dtcc-priority1-20261009/raw/`.

Fourteen worksheet regions contain 13,870 rows and 3,051,936 derived bytes.
The exporter preserves cell values/types, column order, identifier text and
leading zeros, blank rows and every original grid in an audit. Selection of a
header row is an explicit investigative choice in workbook-selections.json;
no provider-approved record boundary is claimed. Every JSON roundtrip compared
equal to the selected worksheet cells. Preambles stay in pinned grid audits.
No source data was cleaned or joined.

[Capture manifest](capture-manifest.json), [derived manifest](derived-manifest.json),
[skill report](profile/REPORT.md), [draft findings](profile/findings.yaml).

## Measured results

| Region | Profile rows | Blank rows | Observation |
| --- | ---: | ---: | --- |
| DTC alphabetical participants | 918 | 4 | 914 nonblank account numbers, all distinct after trimming |
| DTC numerical participants | 990 | 3 | Includes series headings; not 987 proven participant records |
| DTC settling banks | 49 | 2 | 47 nonblank, distinct ABA representations |
| DTC pledgees | 58 | 1 | 57 nonblank, distinct pledgee numbers |
| DTC direct registration | 62 | 1 | 61 nonblank, distinct participant numbers |
| FICC CCIT | 6 | 0 | Member ID unique in this capture |
| FICC GSD | 308 | 2 | 306 nonblank, distinct member-number representations |
| FICC MBSD | 139 | 3 | Names and service fields; no issued member-ID column |
| NSCC members | 5,365 | 0 | 5,364 distinct gustno values: one duplicated identifier group |
| NSCC guide | 1 | 0 | Documentary text, not a membership record |
| MPID OTC | 2,028 | 0 | MPID unique in this worksheet |
| MPID corporate | 1,398 | 0 | 1,396 distinct MPIDs; two repeated groups; composite MPID + clearing broker unique |
| MPID municipal | 1,367 | 0 | MPID unique in this worksheet |
| MPID UIT | 1,181 | 0 | MPID unique in this worksheet |

Trimmed uniqueness is an exploratory statistic, not an approved normalization
rule or identity binding. Account names include account, branch, series and
service qualifiers; no collapsing of slash suffixes was performed.

The data-profiling command ran all fourteen regions, with scan mode full.
Internal elapsed time: 12.1 seconds; command elapsed time: 14.9 seconds.
Nine parts are classed unknown, one reference and four master by the algorithm.
All classifications and designed keys remain unapproved. The report exposes
22 unanswered questions. No MDM kind is created from those suggestions.

## Access and publication

- [DTC](https://www.dtcc.com/support/dtc-directories): page dated September 30, 2026; five current XLSX links, captures verified. A single delivery does not prove refresh cadence or historical membership effective dates.
- [NSCC](https://www.dtcc.com/support/nscc-directories): page says Excel files update monthly and participant-update notices issue weekly; links marked September 2026.
- [FICC GSD](https://www.dtcc.com/support/ficc-gov-directories): public CCIT and GSD workbooks. GSD page and workbook effective date October 8, 2026. Sponsored-member listing moved to member-only MyDTCC on February 10, 2025; it was not requested.
- [FICC MBSD](https://www.dtcc.com/support/ficc-mbs-directories): public workbook effective September 25, 2026.

Automation/redistribution rights remain unestablished. Company overlap,
account-to-Company cardinality, cross-directory identifier namespaces,
publication semantics, multi-delivery persistence, and notice extraction remain
open. No SEC requests, GLEIF archive scans or installed mastering proof ran.

## Next discovery decisions

1. Review the worksheet metadata/data boundary before accepting keys; the full original grids remain available.
2. Resolve the duplicate NSCC identifier and corporate MPID cardinality with source evidence.
3. Review the draft classifications and source namespaces before planning parts.
4. Approve findings only in the operator's exact words, then advance data-onboarding.

Skill gaps and the pending ownership decision are recorded in
[SKILL-GAPS.md](../../../.planning/workstreams/dtcc-enrichment/SKILL-GAPS.md).

A persistent local copy of all raw, derived and grid-audit files is retained at
`~/.local/share/edgartools/clean-mdm/research/dtcc-20261009/`.
Manifests retain the exact executed temporary paths; archived counterparts have
identical content hashes. Raw captures and grids are not committed.
