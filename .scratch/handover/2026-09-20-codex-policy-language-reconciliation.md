# Company continuation: research replay and policy language reconciliation

2026-09-20. Codex owns `codex/company-native-gleif` in the dedicated
`edgartools-platform-company-native-gleif` worktree. This note records the
user-requested rebase and research check before continuing ticket 12. It does
not close the native integration or activate matching rules.

## Rebase and preservation

PR #665 merged into `codex/sec-gleif-company`, not `main`. The new branch carries
the four Company foundation commits, rebased without conflicts onto
`origin/main` `dfe5eefe4179d9da47bf526b365db43e8896dc51`; the resulting checkpoint
is `9e1d03d35ce80acfc6f62c7d4a57a14af8497a75`.
`codex/backup-company-native-before-rebase-20260920` retains the original
`2f036dde66734bb8e61eaaf50216342b095f346b` checkpoint. Other worktrees and
branches were left alone.

The untested XML-only loader draft was preserved outside the repository at
`~/.local/share/edgartools/clean-mdm/drafts/gleif_source_xml_before_policy_language_20260920.py`.
It is not shipped code or verification evidence. The actual research inputs
require JSON ZIP support, and policy decisions must use the new declarative
design rather than accumulating source-specific matching code in that draft.

## Research reverified

[Machine-readable evidence](../clean-mdm/research-reverification-20260920.json)
records artifact hashes, sizes, counts, replay results and limitations.

All three original September 11 16:00 UTC Golden Copy archives were restored
from the URLs in the retained manifest to
`~/.local/share/edgartools/clean-mdm/research/gleif-20260911-1600/`.
Their exact byte lengths, SHA256 digests and ZIP CRCs match the original
manifest. Archives remain outside git.

| Replay | Result |
| --- | --- |
| SEC inputs and deterministic cohort selection | 10,473 snapshot rows; 8,341 eligible rows; identical 1,000-row cohort |
| Retained candidate decisions and finalization | 883 candidates; 308 accepted, 502 no candidate, 103 rejected different, 87 unresolved |
| Level 1 full-archive extraction | 3,428,477 scanned; 316 retained; byte-identical retained extract |
| Relationship full-archive extraction | 487,721 scanned; 2,987 retained; byte-identical retained extract |
| Reporting-exception full-archive extraction | 6,351,397 scanned; 517 retained; byte-identical retained extract |
| Attribute analysis | Byte-identical comparisons and summary |
| Parent/exception analysis | 53 accepted-child accounting records, only 3 with both endpoints accepted; 517 exceptions; Company evidence-pattern counts match |

The old scripts ran against temporary output directories. Original research
artifacts were not rewritten. The full candidate-generation scan and independent
re-adjudication were **not** repeated: this is reproducibility of the retained
research, not independent truth or calibration of a new matching policy.

Implementation consequences:

- These archives are **JSON ZIP**, not XML ZIP. Publication time, counts and
  CDF versions are pinned in the retained metadata manifest; do not invent XML
  headers or derive ordering from filenames/arrival time.
- The 316 Level 1 records include 308 records whose own LEI is accepted and
  eight that merely reference accepted LEIs. Record retention is not a binding.
- Of the 308 own records, 197 registrations are ISSUED, 107 LAPSED, two RETIRED
  and two DUPLICATE. Revalidate the four retired/duplicate links. Lapse alone
  does not revoke a binding under accepted Company Q9.
- Tier B's retained adjudication precision is 224/249 (89.96%); it does not
  establish the accepted Company automatic-rule gate. The 308 research links
  are not independent held-out truth or an activation instruction.
- The approved Company scope, parent closure and independent OpenCorporates
  publication still need explicit pinned inputs. Restoring the historical
  corpus does not silently select it as the complete production/rebuild scope.

## Claude's rules-as-data direction

Read the merged [handoff](2026-09-20-claude-to-codex-mastering-policy-language.md),
[specification](../../docs/specs/mdm/policy-language.md), resolved map and Company
prototype after rebasing. The user explicitly called out this new direction.
Use it as the implementation direction: rules and parameters are immutable,
versioned data; the shared runtime evaluates named, versioned primitives.

Reuse `mdm_v2.policy.body` and the existing batch digest, governed registration,
pre-commit assessments, transaction journal and recovery boundaries. Author
per-kind policies, classify per source, decide binding/consolidation at kind
level and select values per field. Source priority cannot establish sameness.
No additional policy registry or source-specific matching engine is needed.

The merged document remains explicitly **proposed**, with a throwaway
interpreter. `store.register_policy` and `MergeStage` still refuse nonempty
`automatic_rules`; production evaluation of this language is not implemented.
The prototype's checker was rerun: all six advertised refusal cases were
refused; Person classification reproduced 841/841, 353/353 and 26 deferred on
the retained 1,220-row sample. This checks that prototype's classification
behaviour, not Company binding, field survivorship or PostgreSQL integration.
Its original binding primitives are placeholders. The separate 72,981-decision
binding experiment was read but not independently replayed here.

## Reconciliation required before automatic Company decisions

1. **Activation — resolved:** the user selected Identifier Contract activation
   for identifier-only binding (Company Q14) and rejected a separate statistical
   gate for routine reuse of an established master. Exact, compatible identifier
   matches automatically reuse the existing Company ID under a verified contract.
   Fuzzy binding and published-ID consolidation retain their independent
   statistical gates. Runtime predicates and recovery remain to be implemented;
   do not equate the accepted decision with an installed automatic rule.
2. **Company example drift:** the prototype refers to the older seed-link slice,
   placeholder source codes and a published registered address. Current Company
   Q1–Q13 require qualified fuzzy matching, frozen SEC scope and source-only
   GLEIF names/addresses for the first slice. Translate the accepted contract;
   do not register the prototype as a production policy unchanged.
3. **Confidence:** the prototype uses one-sided 97.5%; accepted Company text
   says 95%. Declare and verify coverage explicitly. The Person 99% proposal
   does not change the Company bar.
4. **Schema and replay:** resolve one canonical field layout (the spec shows
   both `kinds.<kind>.fields` and the existing top-level `fields`), classification
   placement and field aliases, per-kind provenance, and bounded re-projection
   after policy edits. Merely adding a kind version beside a whole-body digest
   does not stop Company business-hash churn after a Person-only edit.
5. **Runtime rule suspension:** define the durable replayable counter/suspension
   contract. It must not mutate the registered policy or disappear at batch
   boundaries. The proposal's cross-batch deactivation is not implemented.
6. **Accepted survivorship:** coherent groups and publication-time ordering
   still need implementation and acceptance tests. The prototype did not
   exercise survivorship.

Keep disagreements here, not in Claude's owned map or tickets. Continue Company
ticket 12's native source/consumption work with policy-neutral evidence adapters;
route classification, matching and projection choices through the reconciled
policy contract. Report the next Company ticket before starting it, as requested.

## Rebased foundation validation

`uv run --frozen --extra s3 --extra mdm-runtime --extra mdm pytest
tests/integration/test_clean_mdm_postgres.py
tests/integration/test_clean_source_publications.py
tests/mdm/test_clean_publication_continuity.py
tests/mdm/test_clean_company_source.py -q`

Result: **90 passed in 181.52 seconds; no skips**. Integration tests used
disposable PostgreSQL 16 containers and restricted application roles. This
validates the rebased existing foundation, not the future native loader or
policy interpreter. Persistent MDM databases were not rebuilt.
