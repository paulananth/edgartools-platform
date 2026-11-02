# 168: A publish leaves the term status to the server

Priority: 168. Map: [Rebuild priorities](../map.md). Opened 2026-11-02 07:08 ET (operator, 2026-11-02: "why everything in draft in openmetadata", then "stop forcing Draft on the local catalog").

Type: task. Status: resolved. Blocked by: none.

## Question

Every glossary term was Draft because the publisher patched it so. How does the operator stop that?

Answer: `rules catalog publish --draft-terms` forces Draft; without it the publisher does not touch term status. Off by default.

## Parts

- [x] GoF consult: leave `publish`; one flag passed to the existing `_draft_terms` (2026-11-02 07:08 ET)
- [x] `publish(plan, call, draft_terms=False)` and the `--draft-terms` flag (`test_a_publish_leaves_the_term_status_to_the_server_unless_asked`, `test_a_term_is_written_as_draft_never_approved_when_asked`, 54 pass, 2026-11-02 07:08 ET)
- [x] Live: resumed `GlossaryTermApprovalWorkflow`, published without the flag, read back 22 of 22 terms Approved (2026-11-02 07:29 ET)
- [x] Learning → skill: `skills/openmetadata/SKILL.md` names the flag and that the workflow, not the publisher, now decides
