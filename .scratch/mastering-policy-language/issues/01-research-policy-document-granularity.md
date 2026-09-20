# Research: what is the right unit for one policy document — per kind, per (kind, source), or one for all?

Type: research
Status: resolved
Blocked by: none

## Question

Q4 of the charting grill: the digest pins one whole document per merge
batch, so the unit of versioning matters. Options on the table:

- (a) one document per **identity kind**, with a section per source
  inside it (classification under its source; binding/consolidation at
  kind level because they compare across sources; survivorship per field
  with an ordered source list);
- (b) one document per **(kind, source)**;
- (c) one document for **all kinds**.

The operator wants a simple, clear, easy answer, backed by evidence
rather than preference. Establish, from primary sources:

1. **What Clean MDM's own code and spec constrain.** How is a policy digest
   pinned — per batch, per consumer, per kind? Can one batch carry records
   of more than one kind or more than one source? Read
   `edgar_warehouse/mdm/clean/merge.py`, `store.py` (`register_policy`),
   `consumer.py`, `company_source.py`, `cli.py`, and
   `docs/specs/clean-mdm/merge-stage.md` / `evidence.md` /
   `domain-model.md`. Cite `path:line`. Note in particular whether the
   `fields` block being keyed by kind already implies (a) or (c).
2. **How established entity-resolution / MDM tools scope their match and
   survivorship configuration** — from their primary documentation, not
   blog posts: Splink (settings object: one per linkage job; `link_type`,
   blocking rules, comparisons), Senzing (config: data sources, entity
   types, features, rules), Zingg, Informatica MDM (match rule sets per
   base object), Reltio (match groups per entity type, survivorship per
   attribute), Tamr or Dedupe.io if their docs are public. For each: what
   is the unit of a rule set (entity type? source? job?), where do
   cross-source rules live, and where do source priority / survivorship
   rules live relative to match rules. Two or three sentences each, with
   the URL of the page that says it.
3. **What our own already-written rules need.** The Company contract
   (`.scratch/gleif-company-augmentation/spec.md`), Person tickets 02 and
   03 (`.scratch/person-consumer-contract/issues/`), and the shared
   foundation spec (`docs/specs/mdm-enrichment/shared-foundation.md`):
   list every rule and mark whether it is per-source (classification),
   cross-source (binding/consolidation), or per-field (survivorship), and
   which sources it names. This is the corpus the chosen unit must hold
   without duplication.

Then answer plainly: which unit lets every rule live in exactly one
place, lets a Person change not re-version Company, and fits how the
digest is pinned today — with a one-paragraph explanation the operator
can read without the detail, and the detail beneath it.

Write to
`.scratch/mastering-policy-language/research/01-policy-document-granularity.md`.

## Answer

Resolved 2026-09-20 — [findings](../research/01-policy-document-granularity.md).
**(a′): author one document per identity kind; classify per source; pin the
composition.** The pinned unit cannot be smaller than all kinds: one batch's
closure reaches other kinds through relationships (`merge.py:38-42, 69-78,
97-102`) and every reachable identity is re-projected under the batch's single
digest (`merge.py:179-184, 219-266`; `survivorship.py:200`), so a body missing a
kind silently projects it with zero fields ([§2 reason 1](../research/01-policy-document-granularity.md#2-recommendation-and-reasons)).
Option (b) dies on survivorship: source rank is an ordered list inside a
per-(kind, field) rule (`survivorship.py:203, 240`; `merge-stage.md:127`).
Classification is already per source and runs before the policy loads
(`adapters.py:58-68`; `cli.py:89-95`), so rule C-J belongs with the dataset
contract, which also gives its cross-kind step 1 exactly one home ([§3](../research/01-policy-document-granularity.md#3-clean-mdm-constraints-with-citations),
[§5](../research/01-policy-document-granularity.md#5-the-corpus-of-rules-already-written-in-this-repo)).
The golden-record tools (Informatica, Reltio, Tamr) scope match rules per
entity type and survivorship per attribute with source priority as a
parameter; none scopes by (entity, source) ([§4](../research/01-policy-document-granularity.md#4-how-established-tools-scope-rule-configuration)).
Open: a Person edit still re-hashes the composite digest stamped on Company
fields (`survivorship.py:274`, `consumer.py:98`) — provenance churn, fixed only
if Codex stamps the kind section's own version ([§6](../research/01-policy-document-granularity.md#6-what-could-not-be-determined)).
