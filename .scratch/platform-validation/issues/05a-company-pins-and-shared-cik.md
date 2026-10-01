# Pin Company's part of the merge rules, and count CIK conflicts across kinds

Type: task
Status: in progress (Claude, branch `claude/company-pins-shared-cik`). A code session allowed by the operator: "1 no login needed 2 ok" (2026-10-01). An earlier attempt was deleted on "Test adjust and delete".
Blocks: `05-onboard-person-feed-1.md` (merged before the Person PR)

## Operator rulings

- Q9 of the Person onboarding log: "A" (2026-10-01). A separate code ticket,
  merged before the Person PR: the pinned tests pin Company's part of the
  merge rules only, and it settles how CIK conflicts are counted once a
  second feed carries a CIK.
- Company mastering ticket 15, question 2 (2026-09-29): only the issuer's own
  records count toward an identifier conflict.

## Finding

Adding `rules/merge/kinds/person.yaml` breaks four pinned tests, and shows a
Merge Stage gap. `binding._contract` reads the first kind that declares a
namespace, so only one kind's sources count as issuers. The policy the Merge
Stage reads back from Postgres is `jsonb`, which orders keys by length, so
"person" comes before "company":
- each Company record's CIK would be looked up among Person records only, so
  Company matching would stop finding Companies;
- a CIK held by one kind would not stop the other kind from creating a second
  entity for it.

## Checklist

- [x] CIK across kinds: a namespace's issuers come from every kind's
  contract; a CIK one kind holds sends another kind's record to review. It
  follows the 2026-09-29 ruling (SEC issues every CIK, so both SEC feeds are
  issuers); stated in the PR, no new question (operator: "do not ask me too
  many questions") (2026-10-01 09:02 ET)
- [x] GoF consult on `binding.py` and `activation.check_policy`: leave the
  structure; `company_part` is a filter before the layers, not a layer
  (2026-10-01 09:04 ET)
- [x] `binding.py`: `_contracts` reads every kind; `_issuers` is their union
- [x] `check_policy` refuses kinds whose contracts for one namespace disagree
  on authority or normalizer (unit test)
- [x] Pinned tests compute over Company's part only; zero pinned hashes
  changed (`git diff` has no hex edits):
  - `tests/mdm/policy_layers.py`
  - `test_rules_config_digests.py`
  - `test_clean_activation.py`
  - `test_clean_company_source.py`
- [x] `test_clean_cik_contract.py`: each mapped identifier is issued by some
  kind's contract
- [x] `tests/integration/test_clean_shared_cik.py`, 3 passed (2026-10-01 09:15 ET):
  - a Person's CIK finds its Person;
  - a Company-held CIK sends the Person record to review;
  - a Person-held CIK sends the Company record to review (added on the Spec
    review).
  On the old code one of them fails, whichever kind wins. Finding: the stored
  policy is `jsonb`, which orders keys by length, so "person" comes before
  "company" and the old code would have taken Person's contract. Every
  Company CIK would then have been looked up among Person records only.
- [x] Named files pass locally, each under 5 minutes (2026-10-01 09:12 ET):
  - unit: 150 passed;
  - `test_clean_identifier_binding` 24, `test_clean_stage_binding` 7,
    `test_clean_cik_rule` 6 + 1 xfail;
  - architecture tests;
  - with Person feed 1's rules copied in temporarily, the four pinned files
    and `test_rules_catalog` all pass (159).
- [x] Three-axis `/code-review` (2026-10-01 09:15 ET):
  - GoF: leave it.
  - Standards: the test reuses `core.contract_body()` and `APPLE_CIK`; the
    check uses named variables; comments say why the first contract is safe
    and what the check leaves per kind.
  - Spec: reverse-direction test added. The looser `test_clean_cik_contract`
    pin is stated in the PR. `_check_deterministic` and `_check_creates`
    still say "creates Companies" in their errors (wording only, a follow-up
    for the Person PR).
- [x] PR #769; CI green, all five checks (2026-10-01 09:21 ET)
- [ ] Merge on the operator's word
