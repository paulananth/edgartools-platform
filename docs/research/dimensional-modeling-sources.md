# Dimensional modeling: the sources read

The evidence behind `skills/data-modeling/GOLD.md` and `DIMENSIONAL.md`. Each row says what was read and how; the rules
themselves live in the skills. Re-read a page before it enters a decision record.

| Source | Read how | Used for |
|---|---|---|
| [Kimball Group, dimensional modeling techniques](https://www.kimballgroup.com/data-warehouse-business-intelligence-resources/kimball-techniques/dimensional-modeling-techniques/) | Full page; it names every technique and defines none | The technique list: fact and dimension types, additivity, conformed dimensions, SCD types 0 to 7, hierarchies, late-arriving, audit dimensions |
| [Kimball Group, late arriving fact](https://www.kimballgroup.com/data-warehouse-business-intelligence-resources/kimball-techniques/dimensional-modeling-techniques/late-arriving-fact/) | Full page | Look up the key in effect when the event happened |
| [Activity Schema 2.0](https://github.com/ActivitySchema/ActivitySchema/blob/main/2.0.md) | Full spec | The stream's columns, relationships by entity and time, stated limits |
| [Anchor Modeler repository](https://github.com/Roenbaeck/anchor), its [`docs/ANCHOR.md`](https://raw.githubusercontent.com/Roenbaeck/anchor/master/docs/ANCHOR.md) and [Wikipedia](https://en.wikipedia.org/wiki/Anchor_modeling) | The constructs document in full; the repository README and the encyclopedia article (which carries a conflict-of-interest notice); the project's own site names the constructs only | Anchor, attribute, knot, tie, nexus; sixth normal form and its two exceptions; historization; generated views; benefits and limits |
| [dbt: building a Kimball dimensional model](https://docs.getdbt.com/blog/kimball-dimensional-model) | Full guide | Process steps, hashed surrogate keys, materialization, tests; no SCD coverage |
| [Snowflake: join elimination](https://docs.snowflake.com/en/user-guide/join-elimination) | Full page | RELY conditions and the warning when data breaks a constraint |
| [Snowflake: clustering keys](https://docs.snowflake.com/en/user-guide/tables-clustering-keys) | Full page | When a clustering key pays and how to choose columns |
| Data Vault 2.0 (search summaries: Snowflake, Databricks and dbt blogs, community posts) | Search summary only | Hubs, links, satellites, hash keys, vault under a dimensional mart. The specification by Linstedt and Olschimke was not read |
| Inmon and Kimball comparison (search summaries, including one survey of practitioners) | Search summary only | Normalized core against conformed bus; trade-offs. The authors' books were not read; two papers with unusual identifiers were not used |

Not read: the Kimball SCD type 2 page (404), the Data Vault specification, the anchor modeling papers (the repository's own constructs document was read), DAMA-DMBOK.
