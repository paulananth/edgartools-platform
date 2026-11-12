# Context Center

Part of the `openmetadata` skill: [SKILL.md](SKILL.md) says when to read this.

## Context Center

OpenMetadata 2.0 replaced the Knowledge Center with the Context Center. A
glossary holds entity terms and a `data_class` tag holds a data class; a
platform word stays in `CONTEXT.md`. A process record that nothing else holds,
or a how-to, is an Article.
Articles are pages (found in the server's `/swagger.json`, tested 2026-11-01 on
version 2.0.2):

- Create with `POST /api/v1/contextCenter/pages`: `name`, `pageType`
  `"Article"` and `page` `{}` are required; the text goes in `description`,
  which the server stores HTML-escaped. Set `entityStatus` to `Draft`; do not
  mark an Article approved. The `page` object holds only `publicationDate` and
  `relatedArticles`.
- Read `GET .../pages/{id}`, list `GET .../pages`, and change the text with a
  JSON patch on `/description`. A short fact is a Memory
  (`/api/v1/contextCenter/memories`); an uploaded file is in
  `/api/v1/contextCenter/drive`.
- Not tested: how an Article looks in the screen, and whether an AI agent finds
  it. The documentation says the agent search reads only the facts extracted
  from uploaded files, not Articles or hand-written Memories.

Associate a glossary term with a table only when the term is one relationship
type and the table is that type. Do not tag the kind table with every term
whose heading starts with the domain name. A domain with no kind table but with
a rules file still has its glossary. A proposed table is not a kind table.

A domain has no `relationsGraph` endpoint. Its graph is lineage. Read it with
`GET /api/v1/lineage/domain/name/{domain}?upstreamDepth=1&downstreamDepth=1`.
The current publisher's domain-to-type edges describe permitted endpoint kinds.
They do not prove any relationship. Do not add them. Use the confirmed evidence
gate and scoped repair above; retain type definitions as vocabulary.

The glossary Relations Graph is a different API,
`GET /glossaryTerms/{id}/relationsGraph`. A domain glossary's Relations Graph
page starts at that domain's identity term.
To read a term's own relations rather than the graph, request
`GET /glossaryTerms/{id}?fields=relatedTerms` with the term's id; the
`relatedTerms` rows carry the relation type and the other term. The
`/glossaryTerms` list response carries no relations at all.
A term that mentions another term is not a relation. Do not add an edge
from a definition, a display name, or an Avoid line.
The current publisher also derives identity-to-type edges from permitted kinds;
these are not real relationships. Do not run that path as confirmation. For a
scoped repair, remove only the exact catalog-owned unsupported pair with
`DELETE /glossaryTerms/{id}/relations/{toTermId}?relationType=<that type>`.
Preserve unrelated curation; absence from a configuration-only plan is not
enough to delete another person's link.
The separate RDF glossary graph stays unused unless that service is enabled.

`rules catalog publish` applies the built-in certification and the `data_class`
tags below. It leaves each term's status to the server unless `--draft-terms` is given
(operator, 2026-11-02: "stop forcing Draft on the local catalog"). It writes the terms, tags and
descriptions this section names. Use the scoped relationship repair above for
unsupported edges; do not change business definitions in the live catalog.
A second write of mention edges or endpoint domain links is how overstatement
comes back. A relationship type that no file under `rules/sources/` names gets
"(planned: no rule reads this type yet and no link is loaded)" in its asset
description and no term. This configuration-derived suffix does not prove
that no link is loaded; verify that claim against the authoritative store.
Each data product carries the identity term of its
domain, `Suggested`. The store of a table is its native Certification, not a custom
tag (operator, 2026-11-02: "rdm = Gold, MDM = Gold, Silver = Silver"). `check`
reports a table whose class tag or certification is missing.

- `data_class`. One tag for each class the data-modeling skill names and this
  catalog can hold: master data on a kind table, reference data on a code-set
  table, relationship on a relationship-type table, transaction data on a
  registered prepared-store table. Copy the class sentence from `CONTEXT.md`
  where it has one, and from data-modeling where it does not. A proposed table
  in the prepared store has no data class. A source dataset has no data class:
  data-modeling does not name a source class. The metadata class stays unused
  until that store is in the catalog.
- Built-in `Certification`, which is mutually exclusive. It is the asset field
  `certification`, read with `fields=certification`. The screen reads
  `certification.tagLabel`. It is not a member of `tags`. A patch that adds
  `Certification.Gold` or `Certification.Silver` to `/tags` can echo the tag
  and leave the version unchanged; that did not certify the asset. Set
  `certification` itself. `Certification.Gold` on every table in the master
  store and the reference store. `Certification.Silver` on every table in the
  prepared store, including a proposed table. Do not certify a captured source
  dataset. Do not put Gold on the prepared store or Silver on the master store.
  Bronze stays unused until a captured-source certification is configured.
  `assetCertificationSettings` supplies the validity period. On this server it
  is 30 days. Record the applied date and the expiry, and apply it again when
  it expires. Do not invent a longer window.

Leave every other built-in classification in place. A repeat put keeps the same
glossary, term, classification and tag identity. Read tags back on their own.
A glossary is global: resetting a database service does not remove it.

Pinned create schemas expose `domains` as FQN strings on applicable resources.
Table registration can also name `dataProducts`. Readback resolves these into
entity references. Request `fields=domains` on its own. The default table
payload omits domain membership, so a missing field is not proof the link is
absent. Compare returned domain FQNs as a set: the server does not keep the
submitted order. Do not compare an input string list directly to a returned
reference list.
