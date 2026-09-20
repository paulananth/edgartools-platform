# Confirm the generic legal-entity registry representation

Type: research
Status: resolved
Blocked by: none (graduated from the map's last fog item after ticket 05)

## Question

Workstream 00's own bullet and parent program
[ticket 12](../../mdm-enrichment-program/issues/12-route-international-organizations-through-common-entity.md)
("the shared-foundation specification must define the generic legal-entity
registry representation, source-classification history, ...") — what is
that representation, now that Clean MDM's `mdm_v2` is the sole MDM target?

## Comments

- 2026-09-19: checked `023_clean_mdm.sql` on
  `origin/codex/clean-mdm-integration` (read-only). Operator confirmed
  "yes" to closing the item as answered by existing tables.

## Answer

Already answered by Clean MDM's tables; nothing to design.

There is no separate "common entity registry" under Clean MDM — every
entity kind lives in the same tables:

```sql
CREATE TABLE mdm_v2.identity (
    entity_id uuid PRIMARY KEY,
    kind text NOT NULL CHECK(kind IN ('company','person','security','fund_structure',
                                      'branch','government','international_organization','venue')),
    published_at timestamptz NOT NULL,
    batch_id text NOT NULL REFERENCES mdm_v2.batch(batch_id)
);
```

`international_organization` is already a `kind`. The spec states:

- **Generic legal-entity registry representation** = `mdm_v2.identity`
  (`kind = 'international_organization'`) + the immutable `mdm_v2.assertion`
  rows bound to it (names, addresses, legal form, status, identifiers,
  lifecycle, relationships) + one `mdm_v2.projection` row for the current
  view. Identical shape to Company; only `kind` differs.
- **Source-classification history** = the assertion chain itself: each
  GLEIF publication's `INTERNATIONAL_ORGANIZATION` category is an assertion
  with its `publication_key` and `revision`, so reclassification is a new
  assertion, never an overwrite.
- No `mdm_international_organization` table, no dedicated consumer — as
  parent ticket 12 decided. A dedicated domain is allowed later only when a
  real consumer needs fields or behavior `identity`/`projection` cannot
  hold.

Consistent with [ticket 05](05-define-publication-aggregate-schema.md) Q3:
the spec points at Clean MDM's tables and never redefines them.
