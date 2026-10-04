# Recreate the repository README

User request: recreate the README to correctly reflect current status and requirements. Own documentation branch/worktree; preserve the active parser work and shared checkout.

- [x] Inspect current main, README history, CLI, packaging, workers, CI and source-completion requirements; verified against origin/main 77d5aa13 and actual help, 2026-10-04 07:16 ET.
- [x] Rewrite README around implemented bundle/control/worker architecture, qualification status and AWS target boundaries. Verified current CLI, package and worker code reviewed; 2026-10-04 07:22 ET.
- [x] Document prerequisites, portable installation, checkout setup, store/role requirements, source/form scope and completion gates. Verified metadata, skill setup, role variables and CI checked; 2026-10-04 07:22 ET.
- [x] Remove retired commands/files/deployment claims and route readers to current references; identify historical runbooks clearly. Verified runtime/parsers removed; maintained install.sh verified and distinguished from retired AWS pipeline script; 2026-10-04 07:22 ET.
- [x] Verify links, command/flag examples and documentation consistency against current code. Verified local links and actual argparse help/flags checked; installed command follows tested bundle setup; 2026-10-04 07:22 ET.
- [x] Independent Standards/Spec review, commit, PR and full CI. Verified both reviews, corrected jq prerequisite, committed README, opened PR #812 and passed every job plus CI gate in run 37198691021; 2026-10-04 07:29 ET.

No cloud deployment, migration, Rules activation or merge is included. The broader data-skill goal remains open until source equivalence and the full installed replay proof pass.

## Review

Independent Spec review found no scoped gaps. Standards review identified the missing `jq` prerequisite for script/architecture tests; README now names it. Clarified that MDM migration uses an owner connection before returning to application-role runtime. No code changes or deployment claims.

- [x] Refresh README after sequential merge of #811 and rebase #812 onto current main. Verified GitHub merge 36bb5a65 and updated 18-column status while retaining compatibility gaps; 2026-10-04 07:34 ET.
