# An init mode: the mapping document first, then the rules

Type: build
Status: open
Blocked by: company mastering ticket 22 (data quality), which adds the
critical data elements and the quality file this document describes.

## Outcome

Operator, 2026-09-28:
- "We might need a data catalog and a mapping document".
- "The skill must have a init mode that creates mapping document and
  document which is critical and merge priorities then they are converted
  into rules".

The Rules skill gets an **init** mode. For a new source it first writes a
**mapping document** that people read and approve, then converts it into
the rules files (`source.yaml`, `quality.yaml`, the kind's merge rules).
The document states, per source:
- each source field, the MDM field it maps to, and its identifiers;
- which fields are **critical data elements** (missing: the record becomes
  an exception, never merges, never stops the run; ticket 22);
- the **merge priorities**: which source wins each MDM field, and the
  matching rules in their order.

A **data catalog** lists every source, dataset and MDM field in one place.

## Decided

- 08:18 ET, asked which one people edit after conversion: "Two separate
  things" (a document kept by hand beside the rules).
- 09:57 ET, superseding it, shown that `CONTEXT.md` and the Source Contract
  spec define the Mapping Document as generated, never hand-edited:
  "Initially, machine-generated must be able to edit and update by stewards
  in an easily understandable way for humans research and provide a
  sustainable format". So the init mode generates the document; stewards
  then edit and update it in a format people read easily, and the rules
  follow from it. The format is researched first
  ([research 11](../research/11-mapping-document-format.md)).
  `CONTEXT.md`'s "Do not edit by hand" changes with the chosen format.

## Open

- Where the mapping document and the catalog live, and their shape.
- Whether a check warns when the document and the rules disagree.
- The catalog's scope: sources and MDM fields only, or silver and gold too.
