# How is the entity-kind contribution and completion model decided?

Type: grilling
Status: resolved
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

## Answer

Decided with the operator on 2026-11-13. Fact base:
[05-entity-kind-fact-base.md](../evidence/05-entity-kind-fact-base.md).

### The contributing set

The **merge kinds gate completeness**; `rules entity-types` is the declared map. The report prints
both counts and names the single difference.

| Kind | Declared (`rules entity-types`) | Gating (merge kinds) | Difference |
|---|---|---|---|
| `company` | 7 | 6 | `gleif.reporting_exceptions.v1` — the contract states `company`, but the kind maps no field and no rule for it |
| `person` | 2 | 2 | — |
| `security` | 4 | 4 | — |
| `fund_structure` | 1 | 1 | — |

### Status

- A kind is **`complete`** when every gating contributing source has loaded and the links have run.
- Every other kind is **`partial`**. `blocked` is reserved for a kind whose load was refused
  outright; nothing today is in that state. **The security kind is `partial`, not `blocked`** —
  `sec.ownership/security_symbols` has zero runs, which is missing evidence, not a refusal.
- The **explained count does not gate the status**. It is recorded as an unchecked item
  (`explained_count_status: "not_checked"`), because no retained export carries it and the live
  read-side check is behind the closed credential gate. The report never asserts that it is zero.

### What gates and what does not

- **Gates:** each contributing target's own completion. The kind takes the **worst** contributing
  target's status.
- **Does not gate:** a declared link step. `links` is reported per target (`complete`,
  `not_evidenced`) and never changes a kind's status. `gleif/mastering` and
  `sec.nport.security/mastering` both have `links: not_evidenced` (0 retained intervals, every run
  still `running`); `sec.nport.fund/mastering` has `links: complete`.
- **Does not gate:** deferred records. `records`, `deferred`, `blocking_deferred` and `open_reviews`
  are reported per contract, plus a kind-level `blocking_deferred` total, and never move a status.
- A source **contributes** when at least one of its contributing targets produced records.
  `gleif/subfund-pairs` carries no kind of its own: it never contributes to company completeness on
  its own, and appears under the security kind's link status.

### Timestamps

- `first_verified_contribution_at_et` is the **earliest verified completion** among the kind's
  contributing targets — the moment the kind actually gained records. Not the earliest run created.

### The resulting rows for the retained evidence

| Kind | Status | First verified contribution (ET) | Gating target statuses |
|---|---|---|---|
| `company` | `partial` | 2026-11-10 22:04:11 | `sec.company/mastering` complete, `sec.nport.registrant/mastering` complete, `iapd.adv/mastering` complete, `iapd.adv/custodians` partial, `gleif/mastering` partial (0 of 7) |
| `person` | `partial` | 2026-11-11 23:22:36 | `sec.submissions.person/mastering` complete, `sec.ownership/mastering` partial (8 of 9) |
| `security` | `partial` | 2026-11-10 22:26:58 | `sec.thirteenf.securities/mastering` complete, `openfigi/mastering` partial (18 of 35), `sec.nport.security/mastering` partial (0 of 6), `sec.ownership/security_symbols` no evidence |
| `fund_structure` | `complete` | 2026-11-11 00:33:20 | `sec.nport.fund/mastering` complete; `links` complete; 7 blocking deferred records reported, not status-changing |

`fund_structure` reads `complete` where the 2026-11-12 snapshot read `partial` — the difference is
the deferred-count rule, not new evidence.
