# Validate the core and review the database design

Type: task
Status: done, in review (Claude, branch `claude/validate-core-and-db-design`)

## Tests (2026-09-30, worktree off origin/main `507a9f00`, each run under 5 minutes)

| Area | Files | Result |
|---|---|---|
| Bookkeeping and Journal, no database | `tests/unit/test_configured_bookkeeping_contract.py`, `test_bookkeeping_skill_feeds.py`, `test_change_journal_transport.py`, `tests/architecture/test_company_only_acquisition.py` | 73 passed |
| Bookkeeping, PG16 | `test_configured_bookkeeping_postgres.py` | 43 passed (1m44s) |
| Bookkeeping and Journal, PG16 | `test_generated_bookkeeping_postgres.py`, `test_change_journal_postgres.py` | 15 passed |
| Journal, Company route and approval, PG16 | `test_change_journal_{acquisition,source_evidence,skill,mdm}*`, `test_company_only_postgres.py`, `test_rules_approval_postgres.py` | 57 passed (2m26s) |
| Company mastering and rules, no database | `tests/mdm/test_clean_*`, `test_rules_config_digests.py`, `tests/unit/test_rules_*` | 567 passed |
| Company mastering, PG16 | `tests/integration/test_clean_*` except the core file | 113 passed, 1 xfailed (3m16s) |
| Clean MDM core, PG16 | `test_clean_mdm_postgres.py` | 49 passed |
| Company mastering on real data | ticket 27 Proving Run (#762) | 6,414 Companies; 3,052 with CIK and LEI; second pass changed nothing |

## Skill walk-through

The skills' commands were run as written, on a throwaway PG16
(`provision-clean-bookkeeping.py --rules --journal`, then each mode), with
throwaway credentials generated and masked. The container was removed
afterwards.

| Command | Result |
|---|---|
| Provision Bookkeeping, Rules, Journal | works |
| `bookkeeping migrate` (rerun), `bookkeeping runs` | works (idempotent; empty) |
| `change-journal migrate` (rerun), `status`, `events` | works |
| `skills/bookkeeping/scripts/resolve_feed.py` | works |
| `rules init` (rerun migrates), `rules save --version <v> <file>`, `rules status`, `rules pending`, `rules mapdoc check` | works |
| `rules profile`, `rules check` | not built, as the skill says |
| `mdm migrate --model clean` | works |
| `mdm counts` | **fails**: it reads legacy tables (review finding 4) |

## Findings

In `docs/specs/database-design-review-2026-09-30.md`: 11 findings, the
table list, the handoffs between databases, the skills' modes, and proposed
names.

## Ticket statuses corrected (git shows them merged)

- Company mastering 13 (#748), 15 (#747), 17 (#751), 25 (#758), 26 (#759)
  and 27 (#762).
- Rules skill 14 (#757).

Left to their owners, since git shows no merge: company mastering 09, 10
and 12, and rules skill 02. The code they describe appears to exist
(migrations 037–039; rules migrations 001–003), so their owners should
close them.
