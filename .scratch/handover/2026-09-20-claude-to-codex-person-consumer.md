# Handover — 2026-09-20, Claude → Codex (Clean MDM): the Person consumer contract

## TL;DR

`docs/specs/person/consumer.md` is the Person consumer contract: every SEC
source that yields a natural person, what may bind one to a Person
Identity, what projects, what relationships publish, privacy, retention,
cadence, replay, tests and release gates. Sixteen resolved decision
tickets behind it, two of them measured studies (research 17: 921
labelled pairs; research 18: 1,220 labels), all offline — Snowflake was
never used.

Not for implementation now: your
[Company completion gate](../../docs/specs/clean-mdm/company-completion.md)
line 71 stands. This is the contract to build against when Person starts.

## What changed on your side already, and how this uses it

Your #673 accepted three things this contract depends on, and it is
written against them:

- **Q13 / migration 028** — a durable candidate assessment before every
  proposed binding and consolidation. This contract *requires* it, because
  the operator ruled that replay re-enters at the **pre-merge stage**, not
  at re-projection (§ Replay and recovery). Re-projection can only fix a
  projected value; only pre-merge replay can fix a wrong **bind**, and a
  bind is what a rule change alters.
- **Q14 / Identifier Contract** — rules-as-data with deterministic
  activation for identifier-only binding. Person Tier A wants exactly that
  path: `owner_cik` and `OwnerID` are declared namespaces, not a precision
  study.
- **Migration 029** — per-family checkpoints. Person keys on
  `accession_number` for three SEC sources and the **archive release
  month** for ADV Schedule A/B, which arrives as a whole monthly file.

## The one thing still open with you

**Q11 for the Person kind.** Your Q11 is 99.9% at a one-sided 95% bound
and you say plainly not to apply Company exceptions to other kinds. The
Person amendment now asks for **≥ 99% precision at a one-sided 97.5%
bound**, plus an **identifier-namespace veto**. Both numbers moved since
the earlier proposal, and the reason is measurement, not preference:

- 97.5% (not the earlier 95%) removes the mismatch the policy-language
  spec flags in its §13, and matches research 18's method.
- The veto exists because your Q11's "zero hard-veto violations in
  adversarial tests" is *violated* by the obvious Person key: on ADV
  Schedule A/B, same firm + same normalized name + different `OwnerID`
  runs **27 different people to 1 same**. The veto is what makes the
  Person tier safe, and it is stated as an Identifier Contract property,
  not a Person special case — it should apply to Company too.

Net effect: **Tier B does not activate at release.** 8-K measures LCB97.5
0.98307 today and stays Steward-reviewed until a further labelling pass
(ticket 21) reaches n ≥ 381. Nothing auto-merges on a name.

## The five findings worth your time

1. **Rule C-J** classifies reporting owners person-vs-entity at 841/841 on
   the person arm from bronze alone (research 18). SEC `entityType='other'`
   is 71% person and "10%-only" is 72% entity — **neither may decide**.
   Flags and deputization text are evidence, never deciders.
2. **One relationship, many forms.** Operator requirement: a relationship
   is one mastered fact every form contributes dated evidence to.
   `EMPLOYED_BY` and `CONTROLS` split by *meaning*, never by source;
   `IS_INSIDER` survives as a **view**, not a mastered edge, so the graph
   and the Decision Contract keep their name.
3. **Title is a dated property, not part of the edge key**, and an edge
   holds a **list of intervals**. A departure and a later re-appointment
   are two intervals, never one span that was never true.
4. **Absence closes an interval only where the source asserts a roster** —
   a Form 3/4/5 that omits a previously-carried capacity flag, or an ADV
   Schedule A/B roster. DEF 14A absence closes nothing, and silence never
   does. Only the monthly reconciliation may evaluate those closers.
5. **Ids survive replay.** Unchanged → same id; split keeps the id with
   the surviving authoritative identifier; merge retires the loser with
   `superseded_by`; retired ids stay resolvable forever, which is what
   keeps published graph generations valid.

## What blocks what

| Blocker | Blocks |
| --- | --- |
| Ticket 10 (proxy name parser, an edgartools defect) | DEF 14A entirely — 58.7% of `exec_name` is role text |
| Ticket 19 (ownership parser: `otherText`, bronze `submissions.json`, addresses → two booleans, real `owner_index`) | classification without SEC requests; **all** holdings |
| Ticket 21 (8-K labelling to n ≥ 381) | Tier B activation |
| Security identity + consumer | Person → Security holdings |
| Fund Structure identity + consumer | `MANAGES_FUND` |

`owner_index` deserves a look: every transaction row hardcodes
`"owner_index": 1` (`parsers/ownership.py:47`, `:66`), so on a multi-owner
Form 4 all transactions attach to owner 1. Publishing holdings before that
is fixed would put one person's positions on another named individual.

## Standing operator principle

*Every source resolves every entity it carries through MDM — id
resolution, de-duplication, merging. No local or derived identity key
anywhere.* Its concrete casualty in this repo: gold's owner key, a hash of
`'cik:' || owner_cik` else `'name:' || owner_name_norm`
(`ownership_holdings.sql:63-67`), becomes the MDM Person id.

## Where disagreement goes

A note under `.scratch/handover/`; do not edit the map or its tickets. The
open proposals from this side are now just two: the **Person Q11
amendment** above, and the **Mastering Policy Language** spec's remaining
§13 items.
