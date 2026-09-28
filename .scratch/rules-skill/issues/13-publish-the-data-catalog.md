# Publish the Data Catalog to OpenMetadata

Type: build
Status: in progress

## Outcome

Operator, 2026-09-28: "new branch PR that publishes the data catalog to
OpenMetadata". Rulings behind it (ticket 11): the catalog server is
OpenMetadata, published one way from the rules, nobody edits rules in it;
its scope is sources, datasets and MDM fields; it runs first on a laptop
(Colima), hosting in AWS is a later decision.

## Design

- `edgar-warehouse rules catalog plan|publish`, from the rules files alone.
- One OpenMetadata database service, `edgartools-rules`:
  - database `sources`: a schema per source (all six, including those that
    feed no MDM kind); a table per feed and per Dataset Contract;
  - database `mdm`, schema `clean`: a table per kind, a column per MDM field
    naming the datasets that fill it, first wins (`mapdoc.winners`, so the
    catalog and the Mapping Document agree by construction);
  - lineage: feed to dataset (table level), dataset to kind (column level;
    an address's parts feed one field, matching-only paths feed none).
- No glossary, tags or classifications: outside the ruled scope. Critical
  data elements are text in the dataset's description.
- `publish` creates or updates, then hard-deletes inside `edgartools-rules`
  only what the rules no longer name. The service description carries a
  sha256 of every rules file.
- HTTP by the standard library: `tests/architecture/test_boundaries.py`
  keeps `httpx` in the SEC client.
- `infra/openmetadata/docker-compose.yml`: OpenMetadata 2.0.2 server, its
  Postgres and Elasticsearch, trimmed from the release's
  `docker-compose-postgres.yml`; no ingestion (Airflow) container; only the
  server's port on 127.0.0.1, so it clashes with no local Postgres.

## Evidence (OpenMetadata 2.0.2, revision c49ec6b1, on Colima)

Probes before the client was written (2026-09-28):
- A name holding a dot is quoted in its fully qualified name
  (`probe-rules.sources."sec.x"."ds.v1"."Entity.LegalName.$"`), and a
  column lineage link by that name is accepted.
- PUT of a table without one of its columns removes the column (version
  0.1 to 1.1); the same PUT again keeps version 1.1.
- PUT of a lineage link with fewer column links replaces them.
- A hard-deleted table takes its lineage with it; re-created, it gets a new id.

Live proof, 2026-09-28 19:27 ET:
- First publish: 15 tables, 6 lineage links.
- Publish again: every table's version unchanged.
- A copy of the rules without SEC's `description` field and without
  `sec.filings`: the column, 1 table and 1 schema deleted.
- The real rules again: 15 tables; Company fed by both datasets, 21 column
  links. `edgar-warehouse rules catalog publish` exits 0.

## Checklist (times ET)

- [x] Branch off main 3a7d5313 (18:25 ET).
- [x] `/gof-refactor-reviewer`: leave the structure; make `mapdoc.winners`
  public and reuse it.
- [x] OpenMetadata on Colima (compose committed); API probed.
- [x] `catalog.py` plan and publish; `rules catalog plan|publish`.
- [x] Tests: `tests/unit/test_rules_catalog.py` (plan covers every source
  and field; lineage; the same rules give the same catalog; publish deletes
  only what the rules no longer name; a server naming a table otherwise
  stops the publish).
- [x] Live proof (above).
- [x] SKILL.md, REFERENCE.md.
- [x] Three-axis review (2026-09-28). Fixed:
  - Standards: a publish deletes only inside `edgartools-rules`, even if the
    server ignores its `service` filter, and removes only lineage from its
    own tables; a server that does not answer is a plain error, not a
    traceback; a test skip that hid the suite without openpyxl.
  - Spec: "Winner" read as though GLEIF never wins; a field now says the
    datasets fill it in order, the first with a value wins. A dataset that
    fills no field says so. Lineage only to fields the merge takes from that
    dataset. The fields the classification rule reads are listed.
  - GoF: the catalog and the Mapping Document share one reader for mapped
    paths (`mapdoc.paths`) and for critical data elements
    (`mapdoc.critical_elements`), so the two cannot describe the rules
    differently.
  - Live proof re-run after the fixes, 19:40 ET: same results.
  - Left as is: identifiers (`cik`, `lei`) are dataset columns, not Company
    fields, as the merge rules have them.
- [ ] PR, CI; merge on the operator's word.

## Not in this ticket

- Hosting the catalog server in AWS.
- Publishing on every merge (CI); for now the skill runs `publish` after a
  rules change is merged.
