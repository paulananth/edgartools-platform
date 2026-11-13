# How is the entity-kind contribution and completion model decided?

Type: grilling
Status: open
Blocked by: 03

## Question

Fact base: [05-entity-kind-fact-base.md](../evidence/05-entity-kind-fact-base.md)
(branch `codex/wayfinder-measure-prod-loads-20261113`, commit `3aa2a51c`).


The report has one row per MDM kind (`company`, `person`, `security`, `fund_structure`). A kind is
`complete` only when every active source contract contributing that kind and every required link
step is verified. The plan forbids inferring the source/dataset-to-kind map from source names and
requires it from active Dataset Contracts (`rules entity-types`).

Decide, with the operator:

1. The exact source/dataset-to-kind map from the active Dataset Contracts in this checkout, and
   whether any kind's contributing set is genuinely ambiguous.
2. What counts as a "required link step" for each kind — for example the `gleif/subfund-pairs`
   link into `sec.nport.security`, the `iapd.adv/custodians` link into `iapd.adv/mastering`, and
   `sec.ownership/security_symbols` after OpenFIGI. Which are hard requirements for a kind's
   completeness, and which are contributions only?
3. The status rule when a contributing source has no verified completion: `partial` versus
   `blocked`, and what distinguishes them.
4. Whether a source's contribution counts as complete when only one of its two targets completed
   (the multi-target sources), or only when every target of that source completed.
5. What `first contribution` means precisely: the earliest verified target completion that
   contributes the kind, or the earliest source completion whose target writes that kind.

Answer with the resolved model, stated as rules a report writer can apply mechanically. Record the
answer in this ticket and append a one-line gist to the map's Decisions so far.
