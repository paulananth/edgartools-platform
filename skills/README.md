# Skills: which one to open

Each skill's own description says when it applies; this page shows how they fit
together. Start at **data-platform** when the task is data work and you do not
yet know which step you are on.

Install every skill for Claude, Codex and Grok from this checkout with
`bash skills/link.sh`, or name the skills to link. An installed command line
copies them instead: `edgar-warehouse skill install`.

| When the task is | Open |
| --- | --- |
| Any data work, from setup to a verified run; finding the next step | [data-platform](data-platform/SKILL.md) |
| **Bring a data set in** | |
| Profile a data set, or compare a new delivery with approved findings | [data-profiling](data-profiling/SKILL.md) |
| Decide where a profiled part sits in the model | [data-modeling](data-modeling/SKILL.md) |
| Onboard a new feed or a new domain | [data-onboarding](data-onboarding/SKILL.md) |
| Turn defects into checks, or audit existing data | [data-quality](data-quality/SKILL.md) |
| Change the mapping, quality or matching rules of a live feed | [refining-rules](refining-rules/SKILL.md) |
| **The operator's rulings for one domain** | |
| Anything about a Security | [security-master](security-master/SKILL.md) |
| Company facts, line items and measures | [company-financials](company-financials/SKILL.md) |
| **Build the engine and its stores** | |
| MDM merge code, migrations, storage adapters, choosing a proof | [mdm-engineering](mdm-engineering/SKILL.md) |
| SQL that must run on more than one database | [sql-writer](sql-writer/SKILL.md) |
| Worklists, leases, checkpoints and recovery of work | [bookkeeping](bookkeeping/SKILL.md) |
| Journal events, receipts and delivery recovery | [change-journal](change-journal/SKILL.md) |
| **Run it** | |
| Make the stores operational, run and monitor loads | [data-operations](data-operations/SKILL.md) |
| Timers, sequences and start or stop of a pipeline | [pipeline-orchestration](pipeline-orchestration/SKILL.md) |
| A failed run, a telemetry gap, wasted resources | [production-support](production-support/SKILL.md) |
| Any AWS, Snowflake, Terraform, image or deploy command | [aws-snowflake-operations](aws-snowflake-operations/SKILL.md) |
| **Govern and catalog** | |
| What counts as governed data, and what belongs on a lineage graph | [data-governance](data-governance/SKILL.md) |
| Business domains, glossaries, assets and lineage in a catalog | [data-catalog](data-catalog/SKILL.md) |
| Reading or writing the catalog on OpenMetadata | [openmetadata](openmetadata/SKILL.md) |
| **General teaching, not this platform's rules** | |
| What pipelines, warehouses and data engineering are | [data-engineering-fundamentals](data-engineering-fundamentals/SKILL.md) |
| Analysing a data set end to end | [data-scientist](data-scientist/SKILL.md) |

## What a skill holds

- The rule and the method, written for any reader. A ticket number, a pull
  request number, the date of a ruling or a run, and one run's counts or
  timings belong in the ticket. A limit the engine enforces is a rule and stays.
- A `SKILL.md` under 500 lines. A section only some tasks need moves whole to
  a sibling file, and its heading stays with one line saying when to read it:
  `python3 scripts/dev/move_skill_section.py`.
- A source, kind or identifier is named only under a heading that contains
  "Examples", except in the skills whose purpose is one domain or deployment.
- A new skill is a folder with a `SKILL.md`; add its row to the table above.
