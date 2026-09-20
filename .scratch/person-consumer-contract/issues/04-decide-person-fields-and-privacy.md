# Decide the projected Person field set, privacy classification, and retention

Type: grilling
Status: resolved 2026-09-20
Blocked by: none

## Answer

**The Person projection** (operator decisions Q1–Q8, 2026-09-20; fast,
easy reads preferred — one row answers "who is this and where do they
serve"):

| Field | Content | Rule |
| --- | --- | --- |
| `legal_name` | survived verbatim by source rank: SEC-registered name for an `owner_cik` > ADV `Full Legal Name` > 8-K `person_name` > proxy `exec_name` | `select_by_source_rank` |
| `display_name` | "First Middle Last" derived from `legal_name` | versioned reorder rule (`name_shape@v`), lives once in the Mastering Policy |
| `name_variants[]` | every name seen: value, source, last observed | retained on the projection so any seen name is searchable without a join |
| identifiers | `owner_cik`s, Schedule A/B `OwnerID`s — each with source, validity | cross-reference ids per ticket 02; never a composite key |
| kind evidence | rule C-J id / version / step | per ticket 03 |
| `roles[]` | one row per (Company/firm identity, role text, capacity): `start_date`, `end_date` (null = no end known), `date_basis` ∈ {`stated`, `observed`}, `last_observed`, `sources[]` | stated (8-K `effective_date`, ADV `Status Acquired`) beats observed (Form 3/4/5 `period`, DEF 14A `fiscal_year`); derived from the same assertions as the relationship edges, same rule version, same batch; **no matching rule may read it** |
| `profiles[]` | `{kind:'adviser', profile_id, crd, status, valid_from, valid_to}` | same-ID profile membership; content belongs to the Adviser contract |
| `last_observed` | max over roles and identifier assertions | freshness for the fast read |

**Retained as source assertions, not projected**: compensation (DEF 14A
six figures, 8-K `compensation_amount`) — bound to the Person, queryable
via assertion history and issuer-keyed gold `executive_records`.

**Not captured into MDM at all**: reporting-owner addresses (Form 3/4/5
XML `reportingOwnerAddress`, owner `submissions.json` addresses). The
parser keeps only `address_is_care_of` and `address_non_us` as
classification evidence. Bronze retains the raw artifact.

**Privacy**: public-record class, no redaction, no new role. Four
structural release gates: no non-public field enters the master; no
derived personal attribute is ever projected; no join to a non-SEC/IARD
source without a new consumer contract; a Steward takedown path retires
a projection (masked `display_name`, roles hidden, assertions kept) on a
recorded decision.

**Retention**: permanent under the foundation contract; no timer, no
dormancy; retirement only by takedown decision.

**Recorded against recommendation**: Q1 (b) roles on the Person — the
operator chose read speed over the (a) invariant-only shape; the three
guards on `roles[]` above are the mitigation.

Consequences for the map: parser-evidence capture graduates to
[ticket 19](19-capture-ownership-parser-evidence.md); the roles summary
and the relationship edges must be defined together in
[ticket 05](05-decide-person-relationships.md).

## Question

A Person is natural-person data. What does the Person projection carry
(name, per-issuer roles and titles with validity, officer/director/10%
capacities, adviser registration where applicable, compensation?), what is
**retained as source assertions but not projected** (compensation figures?
addresses if any source ever carries them?), and what privacy class applies:
who may read the projection, what the API redacts, what the retention rule
is for a Person who ceases to appear in any filing. SEC filings are public
record, which bounds the concern but does not remove it — decide explicitly
rather than by default.

## Grilling log

**Q1 — what is on the Person versus on its edges (2026-09-20).** Operator
chose **(b)**: Person-invariant fields (canonical name, retained name
variants, cross-reference identifiers with source and validity, kind
evidence) **plus a projected roles summary** on the Person, each entry
carrying a **start date and an end date**. Chosen for fast, easy reads —
one row answers "who is this and where do they serve". Recorded against
the recommendation (a): the summary duplicates edge facts, needs its own
survivorship, and widens privacy/retention. Mitigations to carry into the
spec: the summary is derived from the same assertions as the relationship
edges under one rule version; no matching rule may read it (role is not
identity evidence — `CONTEXT.md` Person Identity "avoid: role as
identity"); it re-projects with the edges in the same batch so it cannot
be stale relative to them.

**Q2 — roles-summary row and its dates (2026-09-20).** **(a)**: row grain
= (Person, Company/firm identity, role text, capacity); fields
`start_date`, `end_date` (null = no end known), `date_basis` ∈ {`stated`,
`observed`}, `last_observed`, `sources[]`. A stated date (8-K
`effective_date`; ADV `Status Acquired` for start) always beats an
observed one (Form 3/4/5 `period`, DEF 14A `fiscal_year`); when only
observed evidence exists, `start_date` = first observation, `end_date`
stays null, `last_observed` carries freshness. "Still serving" and
"stopped filing" are therefore never conflated.

**Q3 — compensation (2026-09-20).** **(a) retained, not projected**: DEF
14A figures and 8-K `compensation_amount` are captured as source
assertions bound to the Person, queryable through assertion history and
gold `executive_records` (issuer-keyed), but neither the Person
projection nor the roles summary carries any money field. A Tier B/C
misbind can attach a wrong role (visible, reviewable) but never a wrong
salary to a named person.

**Q4 — addresses (2026-09-20).** **(a) not captured into MDM.** The
ownership parser keeps only two derived booleans (`address_is_care_of`,
`address_non_us`) as classification evidence; no street/city/zip enters
silver, an assertion, or a projection. Bronze retains the raw artifact
as it does everything. ADV Schedule A/B, DEF 14A and 8-K carry no
address. (Parser change joins the ticket 10 / parser-evidence-capture
work.)

**Q5 — name (2026-09-20).** **(a)**: `legal_name` survived verbatim by
source rank (SEC-registered name for an `owner_cik` > ADV `Full Legal
Name` > 8-K `person_name` > proxy `exec_name`); `display_name` = "First
Middle Last" derived by a versioned reorder rule (`name_shape@v`) from
the survived value; `name_variants[]` (value, source, last observed)
retained on the projection so any seen name is searchable without a
join. Source shapes differ (EDGAR conformed `Last First Middle`; ADV
`LAST, FIRST`; 8-K/proxy natural order) — the reorder rule lives once in
the Mastering Policy, not in every reader.

**Q6 — adviser registration (2026-09-20).** **(a) `profiles[]` reference
only**: `{kind: 'adviser', profile_id, crd, status, valid_from, valid_to}`
per governed profile on the same Person id (`domain-model.md:62`
same-ID profile membership). The profile's content belongs to the
Adviser consumer contract; nothing is copied onto the Person. Schedule
A/B owner/control-person rows are `roles[]` entries at a firm, not
registrations. Individual-registrant detection (research 14: no code
tells one from a firm) is that contract's problem, cited here.

**Q7 — privacy class and redaction (2026-09-20).** **(a) public-record
class, no redaction**, readable by any consumer that can read Company;
no new Postgres role (`shared-foundation.md:248`). Privacy commitments
are structural release gates: (1) no non-public field enters the master
(addresses not read, compensation retained-only); (2) no derived
personal attribute is ever projected (no inferred age, gender,
ethnicity, residence, net worth from holdings); (3) no join to a
non-SEC/IARD source without a new consumer contract; (4) a **takedown
path**: a Steward may retire a Person's projection (masked
`display_name`, roles hidden, assertions kept) on a recorded decision
with actor and reason, using the existing decision machinery.

**Q8 — retention when a Person stops appearing (2026-09-20).** **(a)
permanent, freshness visible**: no automatic expiry, dormancy or
masking; foundation retention applies (`shared-foundation.md:270-277`);
`roles[].last_observed` and a Person-level `last_observed` make
staleness readable. Retirement only through the Q7 takedown decision,
never a timer.
