# Mastering steps 1 to 4: what the industry standard says

Researched 2026-11-09. Status: research for the operator, who will approve or reject the wording of steps 1 to 4. Not accepted policy. Terms follow [CONTEXT.md](../../CONTEXT.md).

## Evidence scope

Earlier notes are reused and not repeated: [Informatica merge rules](clean-mdm-informatica-merge-rules-2026-09-17.md), [Ataccama and Profisee merge rules](clean-mdm-ataccama-profisee-merge-rules-2026-09-17.md), [vendor merge rules](clean-mdm-vendor-merge-rules-2026-09-17.md) and [mastering in market EDM products](mastering-in-market-edm-products-2026-11-09.md). That last note holds Opus EDM (formerly Markit EDM, S&P Global EDM) and Rimes. Both publish no match order, no tie rule and no identifier rule. That is not repeated below.

How this note was read, plainly:

- Several vendor pages returned HTTP 403 or 404 to a direct fetch: Informatica documentation, the Reltio support article on crosswalk merging, and some Reltio documentation. Where a fact below says "via search summary", it comes from a search engine's summary of that first-party page, not a full read. Re-read the page before using it in a decision record.
- DAMA-DMBOK is a paid book. No primary text was reachable. Every DAMA point is "unconfirmed".
- ISO standards are paid. Only store listings were reachable.
- No vendor documentation was tested by running the product.

## Table: pipeline stages, industry terms, products, our step

| Stage | Industry term | Products using it | Our step |
| --- | --- | --- | --- |
| Source record arrives | Land, stage, load. Informatica: landing table, staging table, load process. Semarchy: external load with a Load ID. Stibo: Inbound Integration Endpoint (IIEP) import. | Informatica, Semarchy, Stibo, Reltio (data load) | Step 1 |
| Keep the source key beside the master | Cross-reference (XREF) table, source key (`PKEY_SRC_OBJECT`) in Informatica. Crosswalk (source type plus value) in Reltio. Source Record ID in Stibo. | Informatica, Reltio, Stibo | Steps 3 and 4 (our term is "cross-reference table", used for identifiers, see question A) |
| Cleanse and standardize | Enrich, standardize, validate (pre-consolidation). Informatica: cleanse functions in staging. | Semarchy (enrichers, pre-consolidation validation), Informatica, Ataccama (cleansed layer) | Not in steps 1 to 4 |
| Assign the entity type | Not a named stage. The type is fixed by the target: base object (Informatica), entity type (Reltio, Semarchy), partition (Ataccama), object type (Stibo). | All | Step 2 |
| Match | Match, match rules, match group, candidate selection. Rule outcomes: automatic, suspect or potential, manual, non-match. | Informatica, Reltio, Semarchy, Stibo, Ataccama, Profisee, EBX | Steps 3 and 4 |
| Merge or create | Merge, consolidate, link, create golden record. Informatica: consolidation. Semarchy: consolidation. Stibo: merge or golden record. EBX: auto-create golden mode. | Informatica, Semarchy, Stibo, EBX, Reltio, Ataccama | Step 4 |
| Choose field values | Survivorship, with trust (Informatica trust scores, EBX trusted sources, Stibo trusted-source survivorship). | Informatica, Reltio, Semarchy, Stibo, EBX, Profisee | Not in steps 1 to 4 |
| Human decision | Steward task, clerical review, potential matches, matching proposals, duplicate management. | Informatica (manual merge), Reltio (potential matches), Semarchy (duplicate management), Stibo (clerical review), Ataccama (matching proposals), Profisee (steward review), EBX (Merge view) | Step 4 |
| Result record | Golden record (Reltio, Semarchy, Stibo, EBX, Profisee). Master record (Informatica, Semarchy). Base object (Informatica). | Same | Steps 1 and 4 |

Terms in the request, with their home: "base object" and "master record" are Informatica Multidomain MDM terms. "Crosswalk" is Reltio's term. "Cross-reference (XREF)" is Informatica's term. "Source key" is Informatica's `PKEY_SRC_OBJECT`. "Steward task" is a generic phrase. No product page read uses it as a product term. "Match and merge" is used by Semarchy, Stibo, Reltio and EBX as a section name.

## A. The standard pipeline

The standard pipeline is: land the source record, cleanse and standardize it, match it against the golden records, merge it into one or create a new one, then survive the field values. A human steward handles the cases the rules will not decide.

Informatica Multidomain MDM names the stages in its own terms. A load process puts the record in a staging table, then in the cross-reference (XREF) table, then in the base object. On a load insert the process "inserts a record into the cross-reference table associated with the base object", and a new base object record gets consolidation indicator 4, "ready for match". Match then flags candidates and consolidation merges them. The master record carries indicator 1. These details come via search summary of the 10.3 to 10.5 Configuration and Data Steward guides, for example [load inserts and target base objects](https://docs.informatica.com/master-data-management/multidomain-mdm/10-4/configuration-guide/part-4--configuring-the-data-flow/mdm-hub-processes/load-process/run-time-execution-flow-of-the-load-process/load-inserts-and-target-base-objects.html) and [how the consolidation indicator changes](https://docs.informatica.com/master-data-management/multidomain-mdm/10-3/data-steward-guide/introduction/key-concepts/data-consolidation-process/how-the-consolidation-indicator-changes.html). The XREF key is the pair of source key and source system: "a unique key representing the combination of the PKEY_SRC_OBJECT and ROWID_SYSTEM columns" ([cross-reference table columns](https://docs.informatica.com/master-data-management/multidomain-mdm/10-5/configuration-guide/part-3--building-the-data-model/building-the-schema/configuring-base-objects/cross-reference-tables/cross-reference-table-columns.html), via search summary). Trust and survivorship are covered in the [existing note](clean-mdm-informatica-merge-rules-2026-09-17.md).

Semarchy xDM documents the same order under the name "certification process": enrichment and standardization, validation, matching, consolidation, post-consolidation validation. Source records are "pushed into the hub by middleware systems on behalf of upstream applications". When matched and consolidated "these records are referred to as master records". The consolidated, certified result is the golden record ([certification process, xDM 5.3](https://semarchy.com/doc/semarchy-xdm/xdm/5.3/Design/data-certification/certification-process.html)). That documentation is for 5.3, which Semarchy's own page marks as no longer supported.

Reltio's record of origin is the crosswalk: "A crosswalk is a unique identifier, similar to a primary key in a relational database" ([define crosswalks](https://docs.reltio.com/en/model/construct-your-data-model/define-or-refine-your-data-model/define-crosswalks-for-data-sources)). Each attribute value is tied to a source through a crosswalk. A crosswalk has a source type and a value ([crosswalk search summary](https://docs.reltio.com/infoandconfig/configuringcrosswalks.html)). Reltio also gives every entity its own Reltio ID, with a crosswalk to it.

Stibo STEP names its pieces Match Codes, a Matching Algorithm, an Event Processor and an Inbound Integration Endpoint. It can either merge matching records or build a golden record, and source records then stay linked or are merged into it ([Matching, Linking, and Merging](https://service.stibosystems.com/documentation/latest/content/mtchlnkmrg/matchlinkmerge.html), via search summary). The endpoint imports source values, matches them to existing golden records and merges the surviving values ([IIEP match and merge](https://doc.stibosystems.com/doc/version/2025.2/web/content/dataexc/iiep/creatingiiep/iiep-configmatchmergeimpproceng.html), via search summary).

TIBCO EBX (now Cloud Software Group) has a Match and Merge add-on built on four configured parts: table declaration, process policy, matching policy and survivorship policy. A merge policy has an auto-create-golden mode. One option creates a golden record "for duplicates and singletons". The other creates one only when a positive match is found. A merged record keeps a pointer to its target ([EBX Match and Merge add-on, merge policy settings](https://docs.tibco.com/pub/ebx-addon/latest/doc/html/mame/admin_guide/configuring_merge_policy_settings.html), via search summary; the live URL now redirects to docs.onebx.com).

Profisee, Ataccama, Opus EDM and Rimes are covered in the existing notes. Profisee presents matching, logical merging and survivorship as separate steps. Ataccama separates source, cleansed, matching and master layers.

One finding matters for our wording. In Informatica, Reltio and Stibo the XREF or crosswalk holds the source's own key for one source record. It is a record-origin table. Business identifiers such as LEI or ISIN are not in it. They are ordinary attributes, found by match rules. Our "cross-reference table" holds every identifier the record states and looks up golden records by it. That is a wider use of the same word. It is closer to a lookup index than to an XREF. S&P's separate cross-reference service does start from an identifier (BECRS), per the [EDM note](mastering-in-market-edm-products-2026-11-09.md). The difference is worth stating in step 3 so a reader from the industry is not misled.

## B. Matching order: identifier first, fuzzy after

The industry description is that exact matching on a trusted identifier comes first and fuzzy or probabilistic matching handles what remains. Name matching is a normal method beside the others in vendor documentation. No vendor page read calls it a last resort.

Evidence for identifier first:

- Informatica Multidomain MDM supports exact-only base objects and fuzzy base objects with exact, fuzzy or combined columns ([match types](https://docs.informatica.com/master-data-management/multidomain-mdm/10-5-hotfix-4/configuration-guide/part-4--configuring-the-data-flow/mdm-hub-processes/match-process/exact-match-and-fuzzy-match-base-objects.html), from the existing note).
- Semarchy separates entities that are "ID-matched" from those that are "fuzzy-matched". ID matching "produces highly predictable results, as all records sharing the same ID will match and merge". It also says "The matching process differs based on the entity type" ([matching, xDM 5.3](https://semarchy.com/doc/semarchy-xdm/xdm/5.3/Design/matching/matching.html)). The page does not say exact is tried before fuzzy inside one entity.
- Profisee lists deterministic, fuzzy, probabilistic and machine learning methods and a deterministic rule that links records "only when a trusted identifier ... is identical in both". No execution order is stated ([existing note](mastering-in-market-edm-products-2026-11-09.md)).
- GLEIF's duplicate check for LEI records is the clearest ordered example. The filter "first checks the LEI code, then compares registration authorities and registration identifiers". Scoring then uses legal name, legal form, address, jurisdiction and creation date, "to reduce false positives" ([GLEIF blog on duplicate detection](https://www.gleif.org/en/newsroom/blog/transforming-data-into-opportunities-metric-in-motion-ai-powered-duplicate-detection)). Identifiers select candidates. Name and address score them.
- Reltio relevance-based rules let one rule merge above a score and queue for review below it. Name attributes are ordinary inputs to such rules ([relevance-based matching](https://docs.reltio.com/explore/get-a-crash-course/get-ready-to-turn-your-data-into-action/learn-about-multidomain-mdm/reltio-match-merge-and-survivorship/relevance-based-matching---detailed-explanation), via search summary).

So name matching is a peer method in the products and a scorer after identifiers in GLEIF's process. Our rule that name is a last resort, used only when the record has no other identifier, is stricter than any source read. The same point is in the [existing EDM note](mastering-in-market-edm-products-2026-11-09.md). DAMA-DMBOK text on match order: unconfirmed. Secondary study guides say deterministic rules favor precision and probabilistic rules raise recall at the cost of false positives. They are not primary sources.

## C. Outcomes of matching

The standard has three outcomes. No match: create a new golden record or hold the record. One match: link or merge. Several matches: the products split, and no source read calls it a normal single path.

No match. EBX makes it a setting: create a golden record for singletons, or only for duplicates. Stibo's matching score bands put a score below the lowest threshold in "a non-match", and the page does not say what then happens to the incoming record ([Match and Merge, 2025.2](https://doc.stibosystems.com/doc/version/2025.2/web/content/mtchlnkmrg/match_action/match_and_merge/matchandmerge.html)). Informatica gives a loaded record its own base object row and consolidation indicator. Holding a record with no golden record, as our steps do, is not documented by any vendor read. Unconfirmed.

One match. Reltio has two rule kinds. When an automatic rule is true, "the match group will issue a directive of merge". When a suspect rule is true, "the match group will issue a directive of queue for review", and the pair "appears in the Potential Matches View" ([match group elements](https://docs.reltio.com/matchmerge/groupelementsconf.html)). A potential match that a steward confirms is merged. One that is rejected becomes "Not a Match" (via search summary of Reltio's review pages). Stibo has three score bands: above the auto threshold the "survivor" absorbs and deactivates the other record, between the thresholds a steward decides, below the lowest threshold is a non-match. Informatica has automatic and manual rules. A manual rule gives "sufficient similarity for steward attention but insufficient similarity for automatic merging" (existing note).

Several matches, a record that bridges two golden records. The products differ.

- Ataccama does not merge. "Matching never automatically merges two existing identities." An incoming record that could match several existing groups goes to the strongest candidate, and "for other potential matches, the application creates matching proposals" ([Matching architecture, 17.0.0](https://docs.ataccama.com/mdm/17.0.0/matching/matching-architecture.html)). A steward resolves a proposal by merging.
- Semarchy groups by transitive closure: "if record A matches record B and record B matches record C, then records A, B, and C will belong to the same match group". The group is then consolidated. A steward can confirm or lock a group and split or merge duplicates ([certification process](https://semarchy.com/doc/semarchy-xdm/xdm/5.3/Design/data-certification/certification-process.html), via search summary for the steward actions).
- Reltio with an automatic rule merges. A negative rule demotes every merge directive to queue for review. Reltio's own page says using it "is not encouraged because it affects all the other rules" ([match group elements](https://docs.reltio.com/matchmerge/groupelementsconf.html)). Reltio's pages read here do not say what happens when one entity matches two others.
- Informatica 10.5 SearchMatch returns candidates, match details and an automatic-merge indicator. A client then chooses Merge, MultiMerge or Link (existing note). The reviewed sources do not settle two established identities colliding.
- Stibo and EBX: no page read states what happens when one source record matches two golden records. Unconfirmed.

Two golden records already holding the same identifier. This is a duplicate in the hub. The sources read treat it as a defect to repair, not an ordinary state.

- Reltio enforces uniqueness of the crosswalk. When two entities carry the same crosswalk value, "the platform treats them as representing the same source record and automatically merges them". The merge documentation says automatic merging "can not be disabled as it guarantees crosswalk uniqueness". A Crosswalks Consistency task finds entities that share crosswalks and counts duplicates and merge failures. Parallel loads can create the duplicates ([auto-merge by crosswalks](https://support.reltio.com/hc/en-us/articles/46865721353741-Understanding-Automatic-Merge-by-Crosswalks-and-Duplicate-Relationships), [consistency task](https://docs.reltio.com/en/explore/get-going-with-apis-and-rocs-utilities/reltio-rest-apis/engage-apis/tasks-api/entity-crosswalks-consistency-task); both via search summary, the first page returned HTTP 403). This is a source key, not a business identifier. Two entities with different crosswalk source types are not treated as the same.
- Informatica's XREF key is unique per source key and source system, so one source key cannot name two base object rows ([cross-reference table columns](https://docs.informatica.com/master-data-management/multidomain-mdm/10-5/configuration-guide/part-3--building-the-data-model/building-the-schema/configuring-base-objects/cross-reference-tables/cross-reference-table-columns.html), via search summary). A search summary did not confirm the one-row rule outright.
- Semarchy: all records "sharing the same ID will match and merge". So an ID-matched duplicate cannot persist after a run.
- Ataccama constraints: different non-null values of a constraint attribute cannot coexist in one group, and a constraint change can force a split with review proposals (existing note).
- GLEIF treats a duplicate LEI as a data quality failure. The rule is "Every LEI is unique and can represent only one entity" and "Each entity can hold only one LEI code". "Preventing duplicate LEI records is therefore essential to preserving trust in the Global LEI System". Detection and remediation happen "before publication". Potential duplicates were "less than 0.2% of all records". The same blog says AI results are combined with "human expertise and oversight" ([GLEIF blog](https://www.gleif.org/en/newsroom/blog/transforming-data-into-opportunities-metric-in-motion-ai-powered-duplicate-detection)). A published GLEIF dictionary has a registration status of DUPLICATE ([check for duplicates dictionary](https://www.gleif.org/lei-data/gleif-data-quality-management/downloads/2021-11-10_checkforduplicatedictionary_v1.2-final.pdf), via search summary).

Can one identifier value belong to two golden records? Not by design for a trusted identifier. Prevention takes three forms in the sources: a uniqueness key (Informatica XREF, Reltio crosswalk), automatic merge that restores uniqueness (Reltio, Semarchy ID-matching), and a steward queue (Ataccama proposals, Stibo clerical review, Reltio potential matches). No source read says an exception queue is the only guard. A uniqueness constraint on a business identifier (LEI, CUSIP) inside a product: unconfirmed. The products guard source keys and matches. They do not publish per-identifier cardinality.

Direct answer to the operator's objection. The industry standard treats two golden records for one trusted identifier as a defect, not a normal outcome. Where it arises, the product either restores uniqueness by merging or sends the pair to a steward. Whether it merges or asks a steward depends on the product. Reltio and Semarchy merge. Ataccama never merges established identities automatically.

## D. Entity type or domain

Products take the entity type from the target the record is loaded into. They do not classify an arriving record. The type is fixed by configuration: the Informatica base object, the Reltio entity type, the Semarchy entity, the Stibo object type, the Ataccama partition. Semarchy states "The matching process differs based on the entity type" (matching page above). Ataccama's partitions "prevent cross-kind comparison" (existing note). Reltio crosswalks apply to entities and to relationships ([crosswalk summary](https://docs.reltio.com/infoandconfig/configuringcrosswalks.html)).

What the products do when a type cannot be decided: no source read documents it. A classification step ahead of the hub, with a "waits" state, appears in no vendor documentation read. Unconfirmed. Many deployments decide the type in the load mapping, outside the product's documentation. That is inference and not evidence.

Relationships to other golden records resolved later: Informatica has relationship base objects ([relationship base objects](https://docs.informatica.com/master-data-management/multidomain-mdm/10-5/configuration-guide/part-4--configuring-the-data-flow/configuring-the-match-process/configuring-match-paths-for-related-records/relationship-base-objects.html), title from a search result, page not read). Reltio relationships have crosswalks. Deferred resolution of a relationship until the target golden record exists: unconfirmed for every product.

## E. Financial instruments and legal entities

The identifier authorities say each identifier names one thing. The issuer to security link is a separate relationship, not an identifier.

- LEI. ISO 17442 gives "A single unique identifier assigned to each legal entity". "Every LEI is unique and can represent only one entity" ([GLEIF, ISO 17442](https://www.gleif.org/en/about-lei/iso-17442-the-lei-code-structure)). Codes are permanent and never reused, per GLEIF's IANA registration ([IANA URN registration for LEI](https://www.iana.org/assignments/urn-namespaces/urn-formal/lei), via search summary). One entity, one LEI is the authority's rule. A duplicate LEI is therefore a registry defect that GLEIF prevents before publication.
- ISIN (ISO 6166). ANNA says ISO 6166 is the standard for unique identification of financial and referential instruments, and that ISINs are issued by National Numbering Agencies under the assignment rules ([ANNA FAQ](https://anna-web.org/faq-page/), [ISIN Guidelines v24, June 2025](https://anna-web.org/wp-content/uploads/2025/06/ISIN-Guidelines-Version-24-Jun-2025.pdf), via search summary). The "one ISIN per identified instrument" wording is from a truncated snippet. Unconfirmed until the full guideline is read. Whether one ISIN may ever name two instruments: unconfirmed.
- FIGI. OMG's specification describes a permanent, semantically meaningless identifier. Bloomberg is the registration authority ([OMG FIGI specification](https://www.omg.org/spec/FIGI/), [OpenFIGI](https://openfigi.com/about/figi), via search summary). "Never reused" appears only in a secondary wiki. Unconfirmed from a primary source.
- CUSIP and CIK. No primary page on CUSIP uniqueness or on CIK was read. Unconfirmed. Do not rely on this note for either.
- GS1 GTIN is the nearest non-financial parallel. A GS1 change notice states a GTIN "must be allocated uniquely". GS1's own architecture group says "one GTIN is one trade item" is not absolute, because reuse rules differ by key type ([GS1 unique identification finding](https://ref.gs1.org/architecture/findings/unique-gs1-identification), via search summary). This is a warning against assuming an identifier is one to one without measuring it. How the GDSN registry rejects duplicates: unconfirmed.

Issuer to security links. Opus EDM and Rimes keep a security master and a party or entity master as separate offerings and do not publish the link ([EDM note](mastering-in-market-edm-products-2026-11-09.md)). No source read states a standard rule for issuer to security links. The standards (ISO 6166, FIGI) identify an instrument. ISO 17442 identifies an entity. The link between them is a relationship that a data product has to carry. Unconfirmed as a published standard.

Identifier uniqueness is a property of the issuer's registry, not of the master. A master has to measure it, because the registry rule can break in the data a master receives. That is what our Identifier Contract does. No vendor publishes an equivalent.

## F. Other standards and bodies

- DAMA-DMBOK2, reference and master data chapter: no primary text reachable. Every DMBOK statement is unconfirmed.
- ISO 8000-110 and 8000-115: the store listings describe requirements for quality identifiers and syntax in an exchange of master data. Part 115 covers how identifiers resolve to the data they represent and leaves out how identifiers are created ([ISO 8000-115 listing](https://www.singaporestandardseshop.sg/Product/SSPdtDetail/0422f7a5-34db-1cde-3a8c-3a131c22ec12), [ISO 8000-110 listing](https://webstore.ansi.org/standards/iso/iso80001102021)). Neither lists a match order or a golden record rule. ISO 22745: no primary page reached. Unconfirmed.
- GS1 GDSN golden record rules: no primary page read states any. Unconfirmed.

## Verdict on our steps 1 to 4

Step 1. Matches the standard. Land a source record, then decide which golden record it belongs to or create one. Difference of wording only: the industry stages and cleanses the record first, and its master identity table holds the source key. Our list of what arrives (source, entity type, identifiers, fields, relationships, source time) is not a published vendor list. Keep it.

Step 2. Partly matches. One entity type per record, with the type fixed before matching, matches how every product works. The type is configured by the target (base object, entity type, partition). The two additions are not documented by any vendor: a classification rule when the source does not state the type, and a waiting state with no golden record when the type cannot be decided. Both are our design. Say so. Relationships resolved later when the target exists: unconfirmed in vendor documentation.

Step 3. Matches in direction, differs in detail. Looking up the golden record by trusted identifier first is the industry order (GLEIF, Informatica exact base objects, Semarchy ID matching, Profisee deterministic). Two differences. First, the industry "cross-reference" holds the source's own key. Ours holds every identifier, so the wording should say so. Second, the per-identifier Identifier Contract (issuer, how many golden records one value may name, how many values one golden record may carry) is stricter than anything published. The registries state the same cardinality rules (LEI one to one). Keep the contract. Do not describe it as industry practice.

Step 4. Differs, and the operator's objection is supported. "One found: join. None found: create or wait" matches the standard. "Every identifier recorded in the cross-reference table" matches XREF and crosswalk practice. "Two found: steward review, never merged silently" is written as one of three normal branches. In the industry, two golden records holding one trusted identifier is a defect. Reltio, Semarchy and Informatica exact matching restore uniqueness by merging. Ataccama never auto-merges established identities and creates proposals. GLEIF treats duplicates as failures to prevent before publication. Our "never merged silently" is closest to Ataccama. The industry does not publish an equivalent for "a second value on one golden record". That check exists in Ataccama as a constraint (different non-null values cannot coexist).

Concrete rewording of step 4 (for the operator to approve or reject):

> 4. One golden record found: the record joins it. None found: the identifier's rule creates a golden record or leaves the record waiting. Every identifier the record states is recorded in the cross-reference table. Two golden records holding one value, or a second value on a golden record whose contract allows one, is an exception. It is a data defect: a duplicate already in the master, a wrong identifier in a source, or a break in the contract. Mastering never merges the two golden records and never picks one by score. It raises a steward task that names the identifier, both golden records and the source record. The source record is not joined to either until the steward merges the duplicates, corrects the identifier or amends the contract.

Two supporting points for that wording, both ours and not industry text:

- Where the contract says one value names one golden record, the cross-reference table enforces it with a uniqueness key on namespace and value, as the XREF and crosswalk do for source keys. The exception then shows as a refused write, not as a stored duplicate.
- An exception is counted and reported. A rising count is a signal about a source or a contract.

Whether the record stays unjoined, or joins the strongest candidate while the steward works (Ataccama's way), is not settled by the sources. See open point 1.

## Open points the sources do not settle

1. Whether an incoming record that bridges two golden records waits or joins the strongest candidate while a steward decides. Ataccama joins the best group. No other vendor documents this.
2. Whether a second value of one identifier on one golden record is an exception in any product. Only Ataccama's constraint rule is close.
3. What any product does when the entity type cannot be decided. No source read documents a waiting state.
4. Whether relationships to a not-yet-existing golden record are held and resolved later. Unconfirmed in every product.
5. Whether name matching is a last resort. No source says so. Our rule is stricter than any published practice.
6. Per-identifier cardinality for ISIN, CUSIP, FIGI and CIK from primary sources. ISIN and FIGI pages were read only through search summaries. CUSIP and CIK were not read at all.
7. How Stibo and EBX treat one source record that matches two golden records.
8. DAMA-DMBOK text on match order, multiple matches and identifier uniqueness. Not reachable.
9. ISO 22745 and GS1 GDSN golden record rules. Not reached.
10. Reltio's handling of one incoming entity that matches two others by an automatic rule. The page read is silent.
11. Opus EDM and Rimes behavior. See the [EDM note](mastering-in-market-edm-products-2026-11-09.md).

## Statements marked unconfirmed in this note

- Every DAMA-DMBOK statement.
- ISO 22745 role. GS1 GDSN duplicate rejection or golden record rules.
- ISIN "one per identified instrument" wording (truncated snippet). FIGI "never reused" (secondary only). CUSIP and CIK uniqueness (not read).
- Any vendor behavior for an entity type that cannot be decided, or for a relationship whose target does not yet exist.
- Stibo and EBX behavior for a record matching two golden records. Stibo behavior for the non-match outcome.
- Informatica: that one source key maps to exactly one base object row (implied by the key, not stated). Behavior of two established identities colliding.
- Reltio: behavior when one entity matches two others. The auto-merge quotes come via search summary of a page that returned HTTP 403.
- Any product enforcing uniqueness on a business identifier such as LEI or CUSIP.
- Informatica, Reltio, Stibo and EBX pages marked "via search summary": re-read each before use in a decision record.
- Opus EDM and Rimes: see the existing note's list.
