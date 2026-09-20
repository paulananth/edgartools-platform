# Measure the `owner_cik` cardinality claim and test deterministic binding at runtime

Type: research
Status: resolved
Blocked by: none

## Question

Ticket 06 Q2 asks what a deterministic rule does when its identifier
claim ("one `owner_cik` → at most one Person") is later violated, and
whether a declared violation tolerance (option c) is worth its moving
parts. Nothing has been measured and nothing has been run: the
prototype's `identifier_cardinality@1` is a stub returning `true`
(`.scratch/mastering-policy-language/prototype/interpret.mjs:92`) and
research 11 left `owner_cik` collision rates as "could not be determined".

Two deliverables, both from data already on disk or in bronze (Snowflake
will not be restored; zero SEC requests):

### 1. Measure the claim

Corpora: the 5,743-row primary corpus
(`.scratch/person-consumer-contract/research/18-owners.jsonl`) and the
101,137-row legacy corpus (bronze `filings/sec/` primaries, parsed the
way `18-classify.py`'s `parse` stage did; the extension run of research
18 downloaded them — re-download to the scratchpad if not cached). Over
each corpus and over their union:

- **Forward direction** — per `owner_cik`, the number of distinct
  normalized owner names (`norm_name` from `18-classify.py:118-123`).
  Report the distribution, and for every CIK with more than one name,
  classify the reason by inspection of a sample: name variant / typo,
  legal name change (marriage, suffix), or a genuinely different person
  (the violation that matters). This is the observed rate of "one CIK,
  more than one person".
- **Reverse direction** — per `(issuer_cik, normalized name)` and per
  normalized name alone, the number of distinct `owner_cik` values.
  Sample and classify: same person with two SEC accounts (the duplicate
  MDM must collapse, Identity Consolidation), or two different people
  sharing a name (not a violation). Compare with research 16's `OwnerID`
  finding (not unique per natural person).
- Restrict the person-side numbers to rows rule C-J classifies `person`
  (use `rule_combo_j` from `18-classify.py`), since the deterministic
  rule only runs on those.
- Report the rates per 10,000 decisions with Wilson intervals, so a
  tolerance can be set from them rather than guessed.

### 2. Run deterministic binding for real

Extend the prototype's binding path with a small in-memory identity
store and make `identifier_match@1` / `identifier_cardinality@1` real:
bind each `person`-classified row by `owner_cik` in corpus order;
detect the moment a CIK would bind to a second Person (or a Person would
acquire a second CIK in the forward direction); implement all three Q2
behaviours as switches — (a) defer the record only, (b) deactivate the
rule on first violation, (c) defer and count against a declared
tolerance — and run each over the union corpus. Report, per option: how
many records bound automatically, how many were deferred, whether and
when the rule deactivated, and what the Steward queue would have
contained. Do not edit `interpret.mjs` in place: copy it to
`interpret-binding.mjs` beside it so the classification result stays
reproducible, and keep the whole thing throwaway and marked as such.

Then answer plainly: what tolerance the measured rate implies, whether
(c) ever trips on real data or only in theory, and whether (a) would have
missed a pattern that (c) catches. One paragraph the operator can read
alone, then the detail.

Write to
`.scratch/mastering-policy-language/research/07-owner-cik-cardinality-and-deterministic-binding.md`
with the scripts and result JSON beside it.

## Answer

- **The claim holds**: 0 genuine "one CIK, two people" in 104,970 rows / 21,727 CIKs (0 of 72,981 C-J person decisions, Wilson upper bound 0.53 per 10,000); all 42 two-name CIKs are variants, typos, nicknames, legal name changes or entity renames, each read by hand.
- **Why**: EDGAR discards any filer-supplied `rptOwnerName` and inserts the CIK's registered name (Ownership XML Tech Spec v5.1 §4.3.2; 5,743/5,743 equal the SGML conformed name) — a name difference on a CIK is a registered account event.
- **Reverse**: 0 same-issuer duplicate accounts in 16,677 person pairs (CRD `OwnerID` runs ~12/10k on the same test, research 16); 6 name-only collisions, all homonyms.
- **Runtime sees alarms, not violations**: ≈ 21 records / 3.6 items per 10k (any spelling difference) or 8 / 1 (unexplained only), every one a false alarm. **(b)** died at decision 3,107 on a middle initial, sending 96% of the corpus to the Steward.
- **(c)** never trips on real data once it counts distinct items, warms up 10,000 decisions and sits at ≥ 5 items/10k (lenient) — and under a synthetic bulk id failure it stopped the rule in 8–48 decisions where **(a)** silently minted 291 bogus Persons (an unbound wrong id never collides).
- **Verdict for Q2**: (a) is sufficient for the data as measured; (c) is insurance against a broken contract, bought with four tuning knobs (predicate, unit, warm-up, threshold) the data cannot price; (b) is unusable.
- [research/07](../research/07-owner-cik-cardinality-and-deterministic-binding.md); `07-measure.py`, `07-run-binding.mjs`, `prototype/interpret-binding.mjs`; `07-cardinality.json`, `07-binding-results.json`, `07-labelled-sample.jsonl`.
