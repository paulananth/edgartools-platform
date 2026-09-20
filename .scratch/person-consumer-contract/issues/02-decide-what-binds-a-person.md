# Decide which evidence may bind a source record to a Person Identity

Type: grilling
Status: resolved
Blocked by: none

## Question

Per source, what is sufficient to bind a record to an existing Person
Identity or create one, given the repo rule that name similarity alone
never binds and Clean MDM's Q11/Q16 disabling unqualified automatic rules:

- `owner_cik` (Form 3/4/5): deterministic — one CIK, one Person?
- CRD number (Form ADV individual registrant): deterministic?
- Proxy and 8-K names: bind only through a deterministic **context key**
  (same issuer CIK + normalized name + consistent role/flag from a
  reporting-owner row), never name alone? Or Steward review only until a
  calibrated matcher exists?

Also: uniqueness (one active CIK per Person, one active CRD per Person) and
the veto when a CIK and a CRD claim the same person but names disagree.

## Comments

- 2026-09-20, Q1 (`owner_cik`): operator chose **(a)** — `owner_cik` binds
  a Person deterministically, one CIK ↔ one Person enforced in both
  directions, second claimant vetoed to Steward review, and only after
  ticket 03 classifies the row as a natural person.
- 2026-09-20, Q2 (CRD): posed as "CRD never binds a Person; ADV attaches as
  a profile on a CIK-bound Person." Operator: "research differences between
  CRD and owner_cik and if needed they need to be merged to form a unique
  identifier; need full understanding before deciding." Opened
  [ticket 15](15-research-crd-vs-cik-identifier-semantics.md); Q2 waits.
- 2026-09-20, Q2 re-posed on research 15: (a) Person by `owner_cik` only,
  ADV owner/executive rows unread for now; (b′) same plus prove what
  `OwnerID` is so Schedule A/B can bind deterministically if it is the
  individual CRD. Operator asked why (b) needs a Steward — answer: only
  because `OwnerID` is unproven; if proven it binds like `owner_cik`.
  Operator: "research OwnerID before deciding." Opened
  [ticket 16](16-research-schedule-ab-ownerid-meaning.md); Q2 waits.
- 2026-09-20, Q2 re-posed on research 16 as "two typed identifiers, both
  deterministic, linked only by a governed decision." Operator corrected
  the framing: "mdm must have one id for one person, these ids must be
  cross reference ids never unique id, mdm must create a unique id to
  reference both, we cannot create duplicate records." Re-posed as: for
  the no-shared-key case, stage the candidate and let a Steward resolve
  before any Person is created (a), vs create-then-merge (b). Operator:
  "(a) but it should auto merge 80 to 99%, don't want to create manual
  work." Surfaced the conflict with Clean MDM's accepted Q11 (≥ 99.9%
  precision before any automatic rule) and proposed a tiered rule with
  Tier B (compound context key) auto-merging at a measured ≥ 99%
  precision bar. Operator: "yes 99% is fine, send proposal to codex."

## Answer

**One Person, one MDM id; every source id is a cross-reference.**

1. **Identity** is `mdm_v2.identity.entity_id`, minted once, immutable.
   `owner_cik` (Form 3/4/5) and `OwnerID` (ADV Schedule A/B individual
   rows) are **cross-reference identifiers** bound to that id — never the
   identity, never merged into a composite key. A Person holds any number
   of them, of any type.
2. **A cross-reference id points at exactly one Person.** A second record
   with an already-bound id is the same Person, deterministically. That is
   how issuer-admitted duplicate CRD records collapse: two `OwnerID`s, one
   Person. A second *Person* claiming a bound id is a hard veto → review.
3. **No Person is created without a match attempt.** Creation is the last
   outcome, after matching against every existing Person.
4. **Tiers, for the no-shared-key case** (a record whose cross-ref ids
   are all unbound):

   | Tier | Evidence | Action |
   | --- | --- | --- |
   | A | shared cross-reference id | auto, deterministic |
   | B | compound context key — same issuer/firm CIK + exact normalized name + consistent role/flag | **auto, once an offline held-out calibration proves the tier ≥ 99% precision** (one-sided 95% lower bound, per Clean MDM's own measurement method); review-only until then |
   | C | fuzzy name, or name across different issuers | Steward review, via the pre-merge candidate table |
   | D | below the review floor | reject, disposition recorded |

   Tier B's bar is **99%, not Clean MDM's 99.9%** — an operator decision
   to minimize manual work, sent to Codex as an amendment proposal for the
   Person kind only ([proposal](../../clean-mdm-person-q11-amendment-proposal/map.md)).
5. **Scope**: reading `IA_Schedule_A_B` is in scope (11,126 identified
   individuals in the archive the platform already downloads); `DE`/`FE`
   rows never create a Person; firm CRD stays an Adviser-profile attribute.
6. Proxy (`sec_executive_record`) rows cannot enter any tier until ticket
   10's parser fix lands; 8-K rows enter Tier B/C only.

Calibration study for Tier B: [ticket 17](17-calibrate-person-tier-b-context-key.md).
