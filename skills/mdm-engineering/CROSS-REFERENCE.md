# Cross-reference completion

Part of the `mdm-engineering` skill: [SKILL.md](SKILL.md) says when to read this.

## Cross-reference completion

Decided (operator, 2026-10-25): the cross-reference becomes the
one table of every identifier, each row the master id, the identifier kind,
the value, matching or lookup only, the source, first and last seen. Built
for one kind first (switched on 2026-10-26): a record may carry a list of values
for one kind; the Merge Stage looks up every matching value: none mints, one
binds, two consolidate automatically where the rule says so (below). The one
table for the other kinds is still to build; until then the rest of this
section holds.

**What a matching rule does with several masters is data on the rule.**
`on_several: merge` merges the masters a record's values reach, the oldest
surviving, only by an identifier whose Identifier Contract states
`consolidates: true` (an identifier that names one thing however it is
listed; never a national number two masters may share). `on_conflict:
first` binds to the one master the rule's value reaches and lists the
values another master holds as the bind's `withheld`. Otherwise: review. A
record in review merges nothing.

**A filer's copy of an identifier it does not issue is lookup only.** A
source the Identifier Contract does not name in `sources` maps it as a
cross-reference; a matching rule naming that source (`on_no_match: wait`;
a rule open to every source never does) reads the cross-reference, finds the master holding the value and binds to
it, but the value is never minted, projected or counted as held, and the
rule may not merge (activation refuses it). A value two masters hold reaches
both, so the record's own `first` identifier still settles the conflict.
Registration refuses a cross-reference only on a namespace the dataset
itself issues (Design 5).

**A rule's merge** is a `merge` decision (`actor: rule:<id>@<version>`, no
survivor named). It names every live merge either side rests on
(`depends_on`), stored or made earlier in the batch; replay applies a merge
after those it depends on, even at the same time. The planner reads the
stored merges, Match Exclusions and their reversals about the masters
reached once per batch; the save repeats that read under the lock, and a
change makes the proposal stale. An excluded pair goes to review.

**Which values a record gives its master** is decided in one place,
`edgar_warehouse/mdm/withholding.py`. Every reader that answers
"which master holds this value" or "which values does this master hold"
runs its own query, then asks it: both stores' holder lookups, the portable
carrier read, name matching's held values, the agent lookup, the planner's
re-delivered records and the master projection. A new rule about which
values count changes that module, never the seven readers (all seven were
edited twice before it existed). The lookup index keeps a
withheld value; the readers drop it.

MDM owns source-record identity bindings, canonical master redirects and
lookup-only cross-references. Keep those roles distinct: a cross-reference
finds records but is never a master's identifier and never merges masters. Binding/merging goes through
approved matching rules or authorized steward decisions, with the kind's
Identifier Contract enforced.
RDM owns versioned code-set crosswalks; they do not resolve source records to
master entities. Use the packaged
[identity/cross-reference guidance](../data-modeling/SKILL.md#3-identity-or-cross-reference).

Onboarding/refining-rules maps lookup-only namespaces through the Dataset
Contract's `adapter.cross_references` and, where required, `adapter.cross_reference_formats`,
separately from `identifiers`. MDM engineering owns their storage, indexed
retrieval, provenance and per-engine integration; data-operations applies the
qualified migration. Retain cross-references with the source readings and
derive their current lookup from that authority, without a second write path.

The governed reader resolves cross-references through indexed source-record
references and their retained readings. A lookup preserves the source and record,
reading/batch provenance, original bound master and current canonical master.
Waiting records can be found with no bound master. Preserve multiple records
sharing one lookup value; that equality alone joins nothing. A retired native
routine or view is not a normal reader interface.

For each selected engine and affected contract, prove mapping/formatting,
indexed lookup, waiting/unbound results, canonical lookup after a merge,
correction/retirement behavior under its publication contract, retained
provenance, migration/grants and unchanged replay. Verify changes commit with
the owning MDM readings and identity state. Storing an opaque field or passing
another engine's tests does not qualify native cross-reference retrieval.
When inputs carry no cross-references, record the profiling evidence for that
scope instead of inventing a mapping or silently omitting the check.
