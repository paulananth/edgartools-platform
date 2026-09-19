# Company integration increment review — 2026-09-19

Scope: changes after rebased integration baseline `e14eb74b` through the
Company/deferred-evidence checkpoint. Sources: AGENTS.md, CLAUDE.md, source
and recovery specifications, tickets 04/05, and code/history. Applied skills:
`code-review` and `gof-refactor-reviewer`.

## Standards

No remaining documented-standard violations or actionable baseline smells
reported by the independent reviewer. Review found that `json.loads("1e999")`
returns infinity despite `parse_constant`; finite-float parsing now defers the
original bytes and PostgreSQL acceptance covers it. Existing legacy CLI lint
findings are outside the modified parser hunk and remain visible as a limit.

## Spec

Three initial findings, all corrected and independently rechecked:

1. Duplicate Company rows and overlapping sample bundles produced different
   assertion IDs because transport metadata entered assertion provenance.
   Native source provenance now excludes transport hashes/paths/line ordering;
   tests cover duplicate delivery and increasing preparation limits.
2. Malformed names could become array values or normalized operation objects.
   Native nullable-text validation now defers those records with reasons.
3. The SQL capability could retain deferred evidence without a blocking review.
   Migration 027 validates source accounting, requires each deferred record's
   review in its batch, and guards durable reviews against premature closure.
   Direct application-role tests include new and previously retained records,
   missing/closed reviews, accounting forgery and atomic rollback.

The first follow-up found the existing-deferred/new-run omission; the final
follow-up verified its fix. Reviewer verification was code inspection; the
primary agent runs PostgreSQL tests and records their results separately.

## GoF

Leave the current module structure in place. The existing configuration-selected
adapter and shared MergeStage provide the required boundary. Code/history did
not justify Strategy, Template Method, a new transaction framework or a new
source registry. No refactoring recommendation remains.

## Scope limits

Deferred resolution, large-component staging, other native adapters, hosted
consumer publication and cutover remain incomplete. This review covers the
bounded increment, not an end-to-end release. Earlier core review attempts
that hit service limits remain documented as incomplete in historical evidence.
