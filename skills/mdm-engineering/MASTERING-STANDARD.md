# Mastering: what the industry does, and where this platform differs

Read this before changing or defending a mastering step: how a source record finds or creates its golden record, what a
matching outcome means, what to do when two golden records hold one identifier, or whether a merge needs a code change
or only configuration. It records what public vendor and standards material says, marks what it does not say, and states
where this platform's rule is its own. Terms follow `CONTEXT.md`. It is evidence for a decision, never the decision.

## The standard pipeline

Land the source record, cleanse and standardize it, match it against the golden records, merge it into one or create a
new one, then choose each field's value (survivorship). A human steward handles what the rules will not decide.

| Stage | Industry term | Here |
|---|---|---|
| Source record arrives | land, stage, load | step 1 |
| Source key kept beside the master | cross-reference (XREF) table, crosswalk, source record id | the Cross-reference (wider: see below) |
| Cleanse and standardize | enrich, validate, pre-consolidation | the source reading and its quality checks, before the Merge Stage |
| Entity type | fixed by the target the record is loaded into (base object, entity type, partition) | step 2 |
| Match | match rules, candidates; outcomes automatic, suspect, manual, non-match | steps 3 and 4 |
| Merge or create | consolidate, link, create the golden record | step 4 |
| Field values | survivorship, with trust per attribute | after the golden record is settled |
| Human decision | steward task, clerical review, matching proposal | the review and exception counts |

**Our Cross-reference is wider than the industry's.** An industry XREF or crosswalk holds the source's own key for one
source record (a record-origin table); a business identifier is an ordinary attribute found by match rules. Ours holds
every identifier the record states and looks golden records up by them, closer to a lookup index. Say so when comparing.

## Matching order

Exact matching on a trusted identifier first; fuzzy or probabilistic matching for what remains. In the practice read, a
name is a peer method in the products, and in the one ordered example a scorer after identifiers (identifiers select
candidates, name and address score them). **Our rule that a name matches only as a last resort, only where no other
identifier exists and only where the name is unique on both sides, is stricter than any published practice.** It is an
operator ruling, so cite it as one, not as the standard.

## Outcomes

| Found | Industry | Here |
|---|---|---|
| None | create a golden record for singletons, or only for duplicates (a setting); a below-threshold score is a non-match | the kind's creation rule creates, or the record waits |
| One | link or merge; a suspect rule queues for review; a rejected pair becomes "not a match" | the record joins it |
| Several | products differ: some merge (transitive groups), some never merge established identities and raise a proposal for a steward, some pick the strongest candidate while a steward decides | see the next section; the platform has not ruled between waiting and joining the strongest |

## Two golden records for one trusted identifier is a defect

The sources treat it as a defect to repair, not a normal outcome. Prevention takes three forms: a uniqueness key (on the
source key), an automatic merge that restores uniqueness, and a steward queue. None says a queue is the only guard.

- Where an Identifier Contract says one value names one golden record, the Cross-reference enforces it with a uniqueness
  key on namespace and value: the exception shows as a refused write, not a stored duplicate.
- An exception is counted and reported; a rising count is a finding about a source or a contract.
- **An identifier is one-to-one only where measured.** The authority's rule can break in the data a master receives, and
  one registry's own architecture group warns against assuming one identifier per item. The Identifier Contract measures
  issuer, how many golden records one value may name and how many values one golden record may carry. No product reads
  publish an equivalent.
- The link between an issuer and its instrument is a relationship the data product carries, not an identifier and not
  evidence that two records are the same entity.

## Entity type

Products take the type from the target; they do not classify an arriving record. A classification rule when a source
does not state the type, and a waiting state when none can be decided, are this platform's design and appear in no vendor
documentation read. Relationships resolved later, when the target golden record exists, are likewise our design.

## Three decisions, kept separate

1. Do these records describe the same entity? (matching policy: join, create, wait, review)
2. May two existing golden identities consolidate? (explicit permission)
3. Which contributed value wins? (survivorship)

A rule that permits the first never grants the second. Attaching a record to one master and consolidating two masters are
different business actions.

## One Merge Stage; configuration before code

- One Merge Stage serves every kind over one assertion shape (kind, evidence, identifiers, fields, relationships, source
  time). The algorithm and its operations (batch and transaction boundaries, idempotency, same-kind joins, conflict
  checks, waiting and release, review, aliasing and reversal, rule families) are code. Entity, source and policy values
  are configuration. It is not arbitrary behaviour expressible in YAML alone, and not a merge class per kind.
- For each kind and source route, write the matrix first: identifiers and their authority; identifier versus lookup-only;
  candidate selectors; conflict checks; missing and multiple-match outcomes; consolidation permission; field source order;
  freshness; clear and retract handling. Mark each cell supported, configuration, or needing a shared primitive. Add
  engine code only for the last.
- A second workflow that needs an existing operation for another identifier extends the matching profile (namespace,
  evidence paths, conflict check). Keep the current behaviour as the first compatibility fixture. Build no plugin
  framework without a demonstrated need.

## Survivorship and explanation

- Source rank is a starting policy; a later arrival alone never makes a source authoritative. Trust is per attribute.
- For each selected field, expose its source assertion, effective time and selection policy, and why the alternatives lost.
  Each merge, review or override keeps the rule version, evidence, actor where there is one, and reason. An ordinary
  identifier join may stay a source-to-master binding without a separate decision row.
- Reversal is proved after later source updates, not only immediately. Define the redistribution of assertions,
  identifiers, relationships and aliases, and the consumer notification. A steward's deliberate split is never silently
  undone by the next automated match.

## Proof for a mastering change

Explicit expected answers for create, join, review, wait and release, field conflicts, correction, unchanged replay, split
exclusion and failure rollback, for each source route, not one generic happy path. Required counterexamples: similar
names with contradictory authoritative identifiers do not consolidate; two people with one name stay separate; an organization
and a person sharing an identifier never join across kinds; a shared symbol or class does not consolidate distinct
instruments; **a bridge (A matches B, B matches C, A conflicts with C) does not bypass the conflict**. Broad fuzzy or
machine-learned automatic merging waits for a measured use case with labelled difficult negatives and a stated false-merge
tolerance; never copy a vendor's accuracy claim.

## Reading the evidence

- A statement taken from a search summary, or from a page that refused a direct fetch, is unconfirmed: re-read the page
  before it enters a decision record. A paid standard or book not read is unconfirmed, not absent.
- Published material shows capabilities, never a vendor's internals, thresholds, tie rules or whether it uses one
  implementation or several. Do not transfer a detail between two versions or products of one vendor.
- If implementation-level comparison is ever needed, ask for a worked demonstration with inputs and expected outputs of:
  conflicting authoritative identifiers; transitive matches with a conflicting third record; equal-priority values and
  null or clear behaviour; a source correction after consolidation; a split followed by replay; an issuer or listing
  reassignment; concurrent conflicting updates.

## Examples

Read while writing this file; none is a ruling.

- Reltio: automatic and suspect rules; the crosswalk is unique and an automatic merge keeps it so; a negative rule that
  demotes every merge to review is documented as discouraged.
- Informatica: exact-match and fuzzy-match base objects; load puts a record in staging, then the XREF, then the base
  object; attribute-level trust.
- Semarchy: ID-matched against fuzzy-matched entities; matches group by transitive closure.
- Ataccama: matching never merges two existing identities; it raises proposals; partitions prevent cross-kind comparison.
- Profisee: deterministic, fuzzy, probabilistic and learned methods; matching, merging and survivorship as separate steps.
- EBX: a merge policy chooses to create a golden record for singletons or only on a positive match.
- GLEIF: checks the identifier first, then registration authority and identifier, then scores name, form, address,
  jurisdiction and date; a duplicate LEI is a registry defect found before publication.
- Standards: ISO 17442 (one LEI, one entity), ISO 6166 (ISIN), the FIGI specification; ISO 8000-110 and 115 cover
  identifiers in master data exchange. CUSIP and CIK uniqueness were not read from a primary source.
