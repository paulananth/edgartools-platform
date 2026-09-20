# Decide which Person relationships publish and their semantics

Type: grilling
Status: resolved 2026-09-20
Blocked by: none (02 and 03 resolved 2026-09-20)

## Answer

**Two published Person relationship types, both source-agnostic**, plus
two deferred ones. A relationship is one mastered fact that every form
contributes dated evidence to — not one edge per form (operator
requirement, Q1).

| Type | Endpoints | Capacities | Status |
| --- | --- | --- | --- |
| `EMPLOYED_BY` (insider association) | Person → Company | `director`, `officer`, `employee` | publishes |
| `CONTROLS` (ownership and control) | Person → Company | `ten_percent_owner`, `owner` (ADV band), `control_person` | publishes |
| Holdings | Person → Security | beneficial owner / reporting person | **deferred** — needs a Security identity with an enabled consumer **and** the `owner_index` parser fix ([ticket 19](19-capture-ownership-parser-evidence.md)) |
| `MANAGES_FUND` | Person (adviser profile) → Fund Structure | — | **deferred** — Fund Structure consumer not enabled |

`IS_PERSON_OF` is gone: same-ID Adviser profile membership
(`domain-model.md:62`, ticket 04 Q6). `IS_INSIDER` is **not** a mastered
edge — it is a published view over the two types filtered to Section 16
capacities, so the graph, the Decision Contract
(`serving/subject_bundle_read.py:148`) and the undeployed API
(`routers/persons.py:59-67`) keep the name they query.

**Identity and time.** Key = (Person, Company, capacity). Title is a
**dated property**, not part of the key, so wording differences across
forms do not split an edge. Each edge holds a **list of dated
intervals**, so a departure and a later re-appointment are two intervals,
never one span that was never true.

**What ends an interval** (Q3): a stated 8-K departure; a later Form
3/4/5 from the same issuer that omits a capacity flag the person
previously carried (these forms restate capacity every time, so omission
is a statement); or absence from a later ADV Schedule A/B filing (a
complete roster). DEF 14A absence closes nothing. Silence never closes
anything — that case is `end_date` null plus `last_observed`.

**Conflicts** (Q6): stated outranks observed via `select_by_source_rank`;
all comparison on **event dates**, never filing dates, so reporting lag
is not a conflict; an affirmative capacity dated after a stated end never
silently reopens the interval — it goes to a Steward.

**Unaccepted far endpoint** (Q7): the edge is a deferred record
(migration 027) that publishes from history the moment the endpoint is
accepted; deferral reasons are counted in run evidence.

**Ticket 04 reconciliation.** `roles[]` is exactly these edges projected:
one row per (Company, capacity, title period), carrying the interval's
`start_date`/`end_date`/`date_basis` and `last_observed`. An `end_date`
on a role row and an interval end on the edge are the same fact, decided
once here. `CONTROLS` rows carry the ownership band. No matching rule
reads either.

## Question

Legacy publishes `IS_INSIDER` (Person → issuer), `HOLDS` (Person →
security, from the transaction tables), `EMPLOYED_BY` (Person → issuer,
from proxy/8-K), and `IS_PERSON_OF` (Person → adviser). Clean MDM's
`domain-model.md` row 62 replaces `IS_PERSON_OF` with same-ID Adviser
profile membership. For each remaining edge: is it kept under the same name
with dated validity and filing provenance; is it published only when both
endpoints are accepted (a Person and an accepted Company/Security); and
what retires it — an explicit later filing, or never by absence?

**Added by ticket 04 (2026-09-20).** The Person projection now carries a
`roles[]` summary — (Company/firm, role, capacity, `start_date`,
`end_date`, `date_basis`, `last_observed`, `sources[]`) — derived from the
same assertions as these edges, under the same rule version, in the same
batch. So this ticket must define the edges **and** that summary together:
which edge each role row is derived from, and what "retires" means on both
at once (an `end_date` on the summary and an edge validity end must be the
same fact, decided once). No matching rule may read the summary.

## Grilling log

**Operator requirement (2026-09-20), answering Q1.** "We need to store all
relationships, not necessarily from the same form; multiple forms will
resolve the person and add the relationship with start date and end date."

So a relationship is **one mastered fact per (Person, Company, capacity)**,
**source-agnostic**: Form 3/4/5, DEF 14A, 8-K and ADV each resolve to the
Person and then contribute dated evidence to the *same* edge, rather than
each form owning its own edge type. That settles Q1 against (b) — legacy's
split of `IS_INSIDER` (Form 3/4/5) from `EMPLOYED_BY` (proxy/8-K) asserts
two facts about one relationship and is not carried forward. `IS_INSIDER`
is retained as a **published view** over the mastered edge, filtered to
Section 16 capacities, so the graph, the Decision Contract
(`serving/subject_bundle_read.py:148`) and the undeployed API
(`routers/persons.py:59-67`) keep the edge name they already query without
a second mastered fact (Q1 option (c)).

**Q2 — edge identity and date accumulation (2026-09-20).** **(a)**: key =
**(Person, Company, capacity)**; **title is a dated property**, not part
of the key, so `"President and CEO"` (Form 4 `officer_title`) and
`"Chief Executive Officer"` (proxy) are two title assertions on one
officer relationship, never two edges; and the edge holds a **list of
dated intervals**, so a 2015 departure and a 2019 re-appointment are two
intervals, never one span that was never true. Legacy's
`dedup_key_fields ["source_entity_id","target_entity_id","title"]`
(`002_seed_data.sql:240-244`) is not carried forward. Ticket 04's
`roles[]` emits one row per (capacity, title period), so the projection
keeps the promotion history; the title normalizer that groups those rows
is display-only — a miss is cosmetic, not a phantom edge.

**Q3 — what ends an interval (2026-09-20).** **(b) stated departures plus
a dated contradiction from a source that asserts or rosters capacity;
never mere silence.** Three closers: (1) an 8-K Item 5.02 departure event
→ `date_basis = stated`, `end_date = effective_date`; (2) a later Form
3/4/5 from the same issuer whose owner row omits the capacity flag the
person previously carried → `observed` end at that filing date (Form
3/4/5 affirmatively restates `is_director`/`is_officer`/
`is_ten_percent_owner` on every filing, so omission is a statement);
(3) absence from a later ADV Schedule A/B filing where the person
appeared before → `observed` end at that filing date (the schedule is a
complete roster of direct owners and control persons). DEF 14A absence
closes nothing — it names only the highest-paid executives, so it is not
a roster. A source that simply stops filing closes nothing, ever; that
case is `end_date` null plus `last_observed`. Legacy's closers are
narrower (`IS_INSIDER` closes only when properties differ,
`pipeline.py:658-720`; nothing closes by absence).

**Q4 — holdings (2026-09-20).** **(a) define the Person endpoint, defer
publication.** The contract specifies the Person side (which Person,
capacity — beneficial owner vs reporting person — reporting period,
units, direct/indirect, derivative flags) and publishes **no** holdings
edge until two gates pass: (1) a **Security identity with an enabled
consumer** exists (`domain-model.md:69` requires Person → Security;
`:63` requires the endpoint kind's consumer enabled — Company and Person
are the only identities today), and (2) the `owner_index` defect is
fixed and re-exported — every transaction row hardcodes
`"owner_index": 1` (`parsers/ownership.py:47`, `:66`), so on a
multi-owner Form 4 all transactions join to reporting owner 1
(`pipeline.py:1979-1980`; `ownership_holdings.sql:38-39`), which would
attach one owner's positions to another named person. Assertions are
captured and bound to the Person meanwhile, so the edge publishes from
history once the gates pass. Both become release gates; the parser fix
joins [ticket 19](19-capture-ownership-parser-evidence.md).

**Q5 — ownership and control capacities (2026-09-20).** **(b) two edge
types by meaning, both source-agnostic**, both keyed (Person, Company,
capacity) with the Q2 interval list and the Q3 closers:

| Type | Capacities | Evidence |
| --- | --- | --- |
| `EMPLOYED_BY` (insider association) | `director`, `officer`, `employee` | Form 3/4/5 flags + `officer_title`, DEF 14A `exec_role`, 8-K Item 5.02 |
| `CONTROLS` (ownership and control) | `ten_percent_owner`, `owner` (with the ADV `Ownership Code` band), `control_person` | Form 3/4/5 `is_ten_percent_owner`, ADV Schedule A/B `Ownership Code` / `Control Person` |

The Q1 split that was rejected was by **form**; this one is by
**meaning**. A 10% holder is not an employee and an officer is not an
owner, and Clean MDM already separates the two at the entity level
(`domain-model.md:61` ownership parent vs `:68` `EMPLOYED_BY`). Distinct
from holdings (Person → Security, deferred in Q4): `CONTROLS` is a dated
relationship to the **company**, not a position in an instrument.
`IS_INSIDER` remains a view, now over both types filtered to Section 16
capacities.

**Q6 — conflicting dated claims (2026-09-20).** **(a) stated beats
observed, compared on event dates, contradictions go to review.** Rank: a
stated date (8-K `effective_date`, ADV `Status Acquired`) outranks an
observed one (Form 3/4/5 `period`, DEF 14A `fiscal_year`) — expressed as
`select_by_source_rank`, not a source-priority table, because the
distinction is assert-vs-observe, not trust. All comparison uses the
**event date**, never the filing date, so ordinary Form 4 reporting lag
is not a conflict (a `period` 2024-03-15 officer flag filed 2024-06-15 is
consistent with a stated 2024-03-31 departure). An affirmative capacity
whose **event date** falls after a stated end is a real contradiction: it
does not silently reopen the interval; it raises a field-level conflict
for a Steward, who either rescinds the end or opens a new interval.
Same-rank disagreement resolves by the later event date. Review volume is
bounded to that one case.

**Q7 — unaccepted far endpoint (2026-09-20).** **(a) deferred, never
dangling, publishes from history.** The Person is created and its
assertions captured regardless. The edge is held as a **deferred record**
(`mdm_v2.deferred_record`, migration 027) naming the unaccepted endpoint
and the reason, and publishes automatically the first time that endpoint
becomes an accepted identity with its consumer enabled — no re-fetch, no
backfill job. Uniform across: unaccepted issuer Companies, unaccepted ADV
firms, holdings (Q4, Security), `MANAGES_FUND` (Fund Structure,
`domain-model.md:70`). Each deferral reason is counted in run evidence.
Legacy dropped these silently (`pipeline.py:1890`).
