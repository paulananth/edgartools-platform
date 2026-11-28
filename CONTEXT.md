# EdgarTools Platform

The shared language for the AWS-first SEC EDGAR data platform: production operator readiness, and the decision-support facts consumed by trading agents (and humans auditing those facts).

## Language

### Bookkeeping work control

Bookkeeping controls work; it does none of it. Workers do the work, each in its own process, and check their own results.

**Worker Profile**:
The name a step's `operation` gives the kind of worker that pulls it, such as `artifact.copy`; a run pins each profile's runtime at its first admitted report.
_Avoid_: Capability, callback, operation handler

**Task Envelope**:
What a worker receives for one unit of work: the frozen work, its live lease, its effect key and the checks it must report. Never an engine, a database or a control method.
_Avoid_: Work item (the control row), job

**Reported Output**:
The output a worker reports for a unit (its *candidate* in the protocol); the unit is complete when Bookkeeping accepts it with the worker's check report. Not a source candidate.
_Avoid_: Result, completion

**Check Report**:
A worker's own check of the output it wrote, bound to exactly that run, step, unit, attempt, effect key and output, with every check the step names.
_Avoid_: Worker success, exit code

### MDM identities and mastering

MDM is the first scope. It masters identities and the relationships between them. A filing or a GLEIF file is evidence for that mastering. It is not itself a master record. Silver, gold, and the parser are outside this scope.

There is one MDM. It is not called "Clean MDM" (operator, 2026-10-13); the old MDM it replaced is deleted.

**Consumable Data Product**:
A governed output made available to an approved operational or analytical consumer. It may present authoritative Golden Records, linked analytical views, published reference values, or governed hierarchies and relationships.
_Avoid_: raw source exposure, schema-wide publication, internal workflow state

**Internal MDM State**:
Ingestion, match resolution, stewardship, reference-data administration, and audit structures used to govern or operate MDM; these are not consumer-facing products.
_Avoid_: Golden Record, analytical product, published reference values

The master data domains are Company, Person, Security, Fund Structure, Branch, Government Entity and International Organization. A profile hangs on one of those domains and is not itself a domain.

**Company Identity**:
The identity of one accepted legal company, shared by its governed Adviser and Audit Firm registrations and, for a business development company, its fund registration. A subsidiary, a filing trust, and its adviser are separate Companies when they have separate identifiers. A rename of one identifier stays one Company, and the old name is an alias.
_Avoid_: A second identity per role, Person, a Fund name as proof of company legal form, merging two Companies because their names are similar

**Person Identity**:
The identity of one natural person, distinct from a Company and shared with an applicable individual Adviser profile.
_Avoid_: Employer identity, role as identity, same name as proof of sameness

**Security Identity**:
The identity of one financial instrument, held by the master id that mastering mints for it. Its CUSIP, ISIN and listing FIGIs are identifiers in the Cross-reference; any one of them finds it, and a source record with none found mints a new one. The Security can exist before its issuer is known. Class A and Class C are two Securities. The reported class title is not the identity.
_Avoid_: A CUSIP or ISIN as the identity itself, one Security per kind of identifier asked, a share class stored on the Company, a second Security for the same CUSIP because a Form 4 used a different title, issuer plus title as proof of sameness

**Security Title**:
The one display title of a Security. A share class is written as the normalized class, such as Class A, and an instrument with no class is written as its kind, such as Option. A title that names neither waits. Each filing keeps the title its manager wrote.
_Avoid_: Inheriting another class of the same Company, the most common filed spelling, every spelling as its own Security, a title stored on the Company

**ISSUED_BY**:
The relationship from a Security to the one mastered issuer. For an operating company that issuer is the Company. For an ETF share it is the Fund Company, the trust that files, not the investment adviser. Filed spellings of that issuer, including an old name, are the same issuer. Each filing keeps the issuer name its manager wrote.
_Avoid_: the sponsor or adviser as the issuer of an ETF share; a security attribute of the Company; a second issuer for a new spelling; a Person as the issuer; a holding

**Relationship Capacity**:
The kind of relationship a natural person holds at a company — director, officer, employee, ten percent owner, owner, control person — and part of that relationship's identity.
_Avoid_: A job title, a source form name, evidence of who the person is

**Relationship Interval**:
One dated period during which a relationship held, carrying whether its dates were stated by a filing or only observed from one, with several intervals per relationship where it stopped and resumed.
_Avoid_: A single span from first to last sighting, an end inferred from silence

**Adviser**:
The governed investment-adviser registration of a Company or a Person. It shares that holder's identity.
_Avoid_: A separate adviser identity, IS_ENTITY_OF, IS_PERSON_OF, the Fund Series it manages, the Fund Company

**Audit Firm**:
A Company that audits other Companies' statements, through its governed audit-firm registration. It shares that Company's identity.
_Avoid_: Audit Firm Profile, A separate auditor identity, a permanent auditor field on the audited Company

**Mastering**:
The one process every source record goes through to find or create the golden record it describes. A golden record is what the rest of this file calls a master identity. No source writes a golden record directly, and no identifier skips mastering.
1. Every source record goes through mastering. It arrives with its source, its entity type, its identifiers, its fields, its relationships and its source time. The first thing mastering settles is the entity type, once, as the record arrives: the source's own where it states one, otherwise decided by classification rules. Each source record has exactly one entity type. A record whose entity type cannot be decided waits, and no golden record is created for it. With its entity type settled, mastering decides which golden record the record belongs to, or creates one.
2. Other things the record mentions are relationships to other golden records, resolved when those golden records exist. A relationship never creates a golden record, and never changes the entity type step 1 settled.
3. Mastering searches the cross-reference table for all the identifiers the source record states, together, under each identifier's Identifier Contract: who issues the value, how many golden records one value may name, and how many values one golden record may carry. Where the record states no identifier, or none finds a golden record, the name rule applies as a last resort: name, former name and place, each an approved rule with its own proof, and a name binds only where it is unique on both sides.
4. One golden record found: the source record joins it. None found by any identifier or by the name rule: the entity type's creation rule creates one golden record, or leaves the record waiting. Two golden records found: this is an error, a duplicate already in the store. Mastering runs its matching rules on the two golden records. If they match, the younger is decommissioned, and the older survivor keeps both golden records' identifiers, source records and history, and the source record joins the survivor. If they do not match, the source record stays unjoined with an exception status until a data steward resolves the duplicate. Every identifier the record states is recorded in the cross-reference table against the golden record it joins or creates.
5. Field values are chosen by survivorship, one field at a time, after the golden record is settled. Source priority, declared per entity type in the mastering policy, decides which source's value survives. It plays no part in deciding which golden record a source record belongs to. Every source's value, including the ones that did not survive, is kept.
6. Every decision is recorded with the rule and mastering policy version that made it, the source records and identifiers it used, and its outcome, so any golden record, and any value it shows, can be explained from its source records.
_Avoid_: A source writing a golden record directly, an identifier class that skips mastering, settling the entity type after searching for a golden record, creating a golden record per identifier before searching the record's other identifiers, source priority as a reason to merge, a score that picks between two golden records

**Merge Stage**:
The common mastering stage that resolves identity before selecting identity and profile values, preserving source attribution, disagreement and the decisions that explain the resulting master state. Merges of one entity type run side by side, including one that creates a master record for an identifier no one holds; one that merges two master records, or creates one by an exact name, runs alone.
_Avoid_: Field overwrite only, source-specific direct master writes, identity consolidation by field priority

**Source Extract**:
The tables taken from one captured file by its contract, together with the receipt that names those bytes.
_Avoid_: Reading, a prediction, Bronze Artifact, Source Capture, Logical Source Revision, Derived Filing Text, Reported Output, Interpretation, Projection, Snapshot, Statement, an extracted temporary file

**Silver Landing**:
Applying the rows of one table of a Source Extract to its registered silver table by key, in batches, with no staging table of its own: a missing key is inserted, a changed one updated, an equal one left alone, so landing the same rows again changes nothing. Source processing owns the rows and that each key appears once in a table; silver only applies them.
_Avoid_: A staging or temporary table in silver, a second duplicate-key check in silver, Reading, Staging

**Source Stage**:
What one source says now about one entity, per field, before any survivorship is applied — read per kind. It holds one record per source record, its newest source extract; a newer source extract replaces it and an older one arriving late does not. A record names the bronze object it was read from, and bronze is the only history of what a source said before. A record waits in the Stage, unbound, until a matching rule links it to an identity.
_Avoid_: Confusing it with the Merge Stage, which is the step that reads it; a history of every source extract (bronze is that); the surviving value, which is the master record's

**Kind**:
The category of a golden record, such as Company, Person, Security or Fund Structure: a code of the RDM code set `mdm-kinds`, with its definition there. How records of a kind are matched and merged is that kind's merge rules, one file per code.
_Avoid_: entity type, domain, a kind kept as a list in code or in a table

**Probable Kind**:
The kind that a rule step gives to a record it holds in the Stage. It sorts the Stage and never creates an identity; the rule of that kind decides.
_Avoid_: hint, candidate kind, a decided kind

**Mastering Scope**:
The records a kind's classification rule masters in the current phase. A record outside it is Set Aside, not lost.
_Avoid_: filter, phase 1 universe, a Set Aside record counted as a defect

**Set Aside**:
A record a classification rule held back by decision, with its reason and Probable Kind: a kind not decided yet, or a ticker no market lists (OpenFIGI does not know it). Gold leaves its links out of a link's test, and it waits for a rule that decides its kind.
_Avoid_: "deferred" alone (a record can also wait on something missing, which is a gap, not a decision), dropped, rejected

**Trading Venue**:
Where a listing trades, named by its ISO 10383 operating MIC. A ticker is unique only within one Trading Venue.
_Avoid_: an exchange name as written, a segment MIC as a venue of its own

**Fund**:
A collection of Securities that pools investors' money. It is not a Company: a fund that is no company is a Fund Structure, and a business development company stays a Company that also holds a fund registration.
_Avoid_: A Security, an ETF share, a name ending in "fund" as proof of the registration, treating a fund as a Company

**Fund Structure**:
A non-company fund arrangement with an evidence-backed structural level and a governed fund registration, whether or not it is a legal person: a registered fund, a privately offered fund or REIT, an exchange-traded commodity or crypto trust, or an insurance company's separate account that pools investors' money. It is distinct from the securities representing interests in it and from separately identified umbrella or subfund arrangements.
_Avoid_: "Fund kind"; treating every fund as a Company; a business development company, which is a Company with a fund registration; treating a fund share as the fund itself

**Fund Company**:
The SEC registrant that files for a fund family, keyed by its CIK. A trust that files for an index fund or ETF family is a Fund Company. The adviser that manages it is not.
_Avoid_: the sponsor or adviser as that registrant; a 13F issuer spelling as a new Company

**Fund Series**:
One fund product under a Fund Company, identified by its SEC series id. It holds Securities. An ETF series is still a Fund Series.
_Avoid_: The traded share, the investment adviser

**INVESTMENT_ADVISER_TO**:
The relationship from an investment adviser to a fund it advises, as Form ADV and N-CEN name the role, with its discretion: discretionary (the adviser decides) or non-discretionary (the client decides). A fund sponsor's investment arm is an adviser.
_Avoid_: IS_FUND-MANAGED_BY (the fund's manager), ownership, ISSUED_BY, the ETF share

**Discretion**:
Who decides about assets: an adviser with discretion decides; without it, the client does (Form ADV Item 5.F). A 13F holding states the manager's investment discretion and voting authority. Discretion is not ownership.
_Avoid_: Beneficial ownership, control

**Branch Identity**:
The identity of a separately identified branch establishment linked to its head office, including where the branch is not a separate legal person.
_Avoid_: Head-office identity, subsidiary Company inferred from branch status

**Government Entity**:
A government body represented in its own right, distinct from a legally incorporated Company whose owner is a government.
_Avoid_: Government ownership as an identity kind, International Organization

**International Organization**:
An organization accepted as that kind from its source category, distinct from a Company and from a Government Entity. It keeps the source classification it was accepted under.
_Avoid_: Company, Government Entity, a new identity for every registry category

**Holdings**:
A position a Person, a Company, or a Fund Series reports in a Security, for one reported period, as filed: a silver row carrying the MDM ids of the holder and the Security, never a relationship MDM masters. A 13F manager's holding carries its investment discretion and voting authority; a Forms 3/4/5 holding its direct or indirect ownership.
_Avoid_: HOLDS (no longer an MDM relationship), ISSUED_BY, INVESTMENT_ADVISER_TO, employment, beneficial ownership inferred from a 13F alone

**AUDITED_BY**:
The relationship from a Company to the Company that audits it for one engagement.
_Avoid_: A permanent auditor field, the Audit Firm profile itself

**EMPLOYED_BY**:
The relationship from a Person to a Company as a director, an officer (with the title) or an employee, for reported dates.
_Avoid_: A holding, ownership (BENEFICIAL_OWNER_OF), treating the person and the employer as one identity

**IS_INTERNATIONAL_BRANCH_OF**:
The relationship from a Branch to its accepted head office. GLEIF relationship records are the evidence.
_Avoid_: A subsidiary Company, the head office itself

**IS_SUBSIDIARY_OF**:
The relationship from an entity to the registrant that lists it as a subsidiary (Exhibit 21). Not accounting consolidation.
_Avoid_: IS_DIRECTLY_CONSOLIDATED_BY, a similar name as proof of ownership

**BENEFICIAL_OWNER_OF**:
The relationship from an owner to an issuer whose securities it beneficially owns, with the percent as filed (Schedules 13D and 13G, Forms 3/4/5). Who owns, not who decides.
_Avoid_: Discretion, a 13F manager's Holdings, IS_SUBSIDIARY_OF

**IS_DIRECTLY_CONSOLIDATED_BY**:
The one direct accounting parent of an entity, which consolidates its accounts (IFRS 10 / ASC 810), in one scope and time, as GLEIF names it; the one direct-parent type for any source. A missing parent is not proof of no parent.
_Avoid_: IS_SUBSIDIARY_OF, beneficial ownership, the ultimate parent

**GLEIF Fund Link**:
A fund-structure relationship as GLEIF states it: IS_FUND-MANAGED_BY (the fund's manager), IS_SUBFUND_OF, or IS_FEEDER_TO. It keeps GLEIF's direction. It does not replace INVESTMENT_ADVISER_TO from Form ADV or N-CEN.
_Avoid_: INVESTMENT_ADVISER_TO, Holdings, reversing the edge to match an SEC filing

**Source Record Binding**:
The evidence-backed assignment of one source record to the Company Identity, Person Identity, or other accepted identity that it describes.
_Avoid_: Combining two existing identities, selecting a winning field value

**Identity Consolidation**:
The decision that two existing master identities describe the same subject and will be represented by one surviving identity, with their prior identities and evidence retained in history.
_Avoid_: Source Record Binding, corporate acquisition, merging fields because their values are similar

**Field Survivorship**:
The rules that select a master field value from eligible source values after identity has been resolved, while retaining the values that were not selected.
_Avoid_: Proof of identity, source rank as permission to merge identities

**Name Matching**:
The last resort of mastering: a record that no identifier finds is matched by its name and its place. It is done by Waterfall Matching, as the last pass of the GLEIF load. It proposes no binding by itself: a name rule may bind only a pair that is one to one in its pass. It is part of the GLEIF merge, not a separate job.
_Avoid_: Name Frequency, Name Census, Census, a matcher, a list of approved pairs, a count over the records a Stage happens to hold

**Waterfall Matching**:
The passes of Name Matching, run from strict to loose. Pass 1 needs the name and the full address to agree; each later pass compares fewer address parts and takes only the SEC filers and GLEIF entities no earlier pass bound. A pair binds only one to one in its pass: the filer agrees with exactly one entity, and that entity with exactly one filer. It runs once, as the last pass of the GLEIF load, over the SEC Companies and the GLEIF records in the store, so the load order cannot change a result.
_Avoid_: a pass over the records one file happens to hold, a separate job run before the merge

**Match Exclusion**:
An evidence-backed decision that specified source records or identities must not be combined while the decision remains in force.
_Avoid_: Low match score, deleting source evidence, a permanent ban without reviewable grounds

**Mastering Policy**:
The versioned, digest-pinned document that declares, per identity kind, the classification, binding and survivorship rules and the proof under which each verdict may act without a Steward.
_Avoid_: A per-source configuration table, a runtime switch, a place to store samples, source rank as an input to sameness

**Identifier Contract**:
The declaration, per identifier namespace, of who issues the value, how many identities one value may name and how many values one identity may carry, the second handle used to detect a violation, and the measurement that verified the claim.
_Avoid_: "The id is unique" as an unstated assumption, a name match standing in for the identifier, a contract without a measurement

**Cross-reference**:
The one table of every identifier a golden record carries, each joined to its golden record id. Every identifier goes through mastering: its entity type's Identifier Contract and matching rules decide whether it finds the golden record a source record joins, creates one, or leaves the record waiting. An identifier no matching rule covers is still recorded on the golden record, and records that share it stay separate until a rule binds them.
_Avoid_: A second identifiers table, a crosswalk, a name that creates a golden record, merging golden records on an identifier no matching rule covers

**Source Contract**:
The one versioned file that declares everything about one source after its Bronze Artifacts exist: how they are read, the silver table they produce, the Dataset Contract that maps them into MDM, and the test cases and batch gate that prove it.
_Avoid_: Source config, pipeline config, adapter config, a contract that also fetches bronze

**Dataset Contract**:
The part of a Source Contract that tells MDM what a source's records are: its authority, record key, publication and time semantics, completeness scope, and the adapter mapping from silver columns to identity kind, identifiers, fields, profiles and relationships.
_Avoid_: Mastering Policy (sameness and survivorship live there, not here), field-alias map as a separate document

**Mapping Document**:
The spreadsheet, first generated from a source's rules, that shows people every source field and the MDM field it fills, its identifiers, its critical data elements, its data quality checks and which source wins each field. Stewards change it; each change becomes the rules only through a reviewed, approved rules version, and a check holds it equal to the rules it was generated from.
_Avoid_: A document that can drift from what runs, a second place the rules live, an edit that acts without an approved rules version

**Data Catalog**:
The published list of every source, dataset and MDM field, with the sources that fill each field in priority order, kept in the catalog server and published one way from the rules.
_Avoid_: A place to author rules, a catalog that differs from what runs

**Rules Database**:
The database that holds every version of every Source Contract and Mastering Policy with its lifecycle state (draft, proven, active, retired), proof and approval, and where Proving Runs execute; an active version is handed to MDM, which production reads.
_Avoid_: Golden merge rule store, editing rules in the production MDM database, a place production merges read from

**Rule Activation Approval**:
The recorded consent of a named person to activate one exact version (by digest) that can bind or merge identities, given only after the agent explicitly asks for it.
_Avoid_: Approval inferred from silence or from an earlier approval, agent self-approval of identity-changing rules

**Proving Run**:
One run of a draft Source Contract or Mastering Policy version's tests and merge, in the Rules Database and never against production identities, whose passing result is the proof that makes the version proven.
_Avoid_: Trial, dry run (the CLI flag that does nothing), canary (a small run on production), calibration (threshold tuning only)

**Artifact Family**:
A named kind of Bronze Artifact that shares one layout and meaning, which a Source Contract reads or looks up by name without knowing where its artifacts are stored.
_Avoid_: A storage path or glob in a contract, a source (one family can serve several sources)

**Primitive**:
One named, versioned, source-independent operation a Source Contract calls with parameters to read or transform a value; the engine provides it and its own tests prove it.
_Avoid_: Inline code or expressions in a contract, a function written for one source

**Named Convention**:
A Primitive that stands for a published format convention used by two or more sources or columns, replacing a chain of small Primitives.
_Avoid_: A home for one source's quirks, a convention used by only one source or column, a convention without its own tests

**Custom Step**:
Code that belongs to one source, lives in that source's folder, is declared in its Source Contract, and takes declared inputs and returns a value, rows or violations without fetching, writing or calling MDM.
_Avoid_: Engine code named after a source, undeclared inputs, a custom step that reaches another source

**Named Case**:
A test in a Source Contract that names what it proves, points at a fixture, and states the expected silver rows, MDM assertions or merge outcomes for the columns that matter.
_Avoid_: A snapshot as the only test, a case named by number, expectations re-recorded silently

**Batch Gate**:
The declared limits a Source Contract version must meet on a pinned batch of real Bronze Artifacts in a Proving Run, each looser-than-zero limit carrying its reason.
_Avoid_: A limit without a reason, an unpinned batch, a gate that replaces a Mastering Policy's precision proof

**Change Journal**:
The append-only record, beside Bookkeeping over every step, of what each source's steps have processed: a whole file or source is identical (already processed under the same rules and shared inputs, so skipped) or is processed; a change in how a source is read, or in a shared input, makes every file of it new again. Bookkeeping restarts a load; the Change Journal says what changed.
_Avoid_: Field- or record-level change (that is the step's own work, and publication's), a journal for mastering only, skipping a file without the operator's force being recorded

**MDM Change Journal**:
The mastering part of the Change Journal: the evidence, decision, outcome and recovery history for mastering within the Change Ledger, joined to the originating Bookkeeping run and MDM Commit Evidence.
_Avoid_: A second root-run authority, mutable log of only the latest result

**IS_ULTIMATELY_CONSOLIDATED_BY**:
The top of an entity's consolidation chain: the entity that consolidates it and that no other entity consolidates, as GLEIF names it. Its basis is stated (a source says it) or calculated (MDM walked the direct parents, keeping the path); both sit side by side. A calculated one keeps its history: a new period each time a link in its chain starts or ends.
_Avoid_: Ownership, an ultimate parent from an incomplete or cyclic chain

**Basis**:
Whether a relationship is stated (a source says it) or calculated (MDM derived it).
_Avoid_: A calculated link read as a source's statement

**SUCCESSOR_ENTITY**:
The relationship from an entity that ceased in a corporate action to the entity that took it over, with the event type and its effective date, as GLEIF names it. On that date the ceased entity's parent links end, and its children's links end unless a source states them again after it; each ended period names the succession.
_Avoid_: A parent, merging the two entities into one

### Data classes, reference data and agent context

**Master Data**:
Data about the things a business deals with, each with its own identity and lifecycle, which grows with the business and is mastered in MDM.
_Avoid_: Any table with a key, reference data, the events about those things

**Reference Data**:
The values that give other data its meaning: a small, near-constant code set, changed only as a whole new approved version.
_Avoid_: Master data, a lookup table copied into a source without a version, free-text labels

**RDM**:
Reference Data Management: where code sets are kept, each changed only by publishing a new approved version, apart from master data.
_Avoid_: MDM, a code list copied into a source, silver, a cross-reference

**Transaction Data**:
Facts and events about master data over time, which only grow, are kept in silver, and point at their masters.
_Avoid_: Master data, a snapshot of master attributes

**Code Set**:
One named list of codes in RDM, with labels, definitions, synonyms, valid dates and versions draft, approved and published.
_Avoid_: An enum in code, a YAML list without a version

**Crosswalk**:
A row mapping a code in one code set version to a code in another, with its match type: exact, close, broad or narrow.
_Avoid_: An unversioned mapping, an implied "same" without a match type

**Reference Hierarchy**:
The grouping of codes inside one code set, one parent code per code, with named levels and a path written when the version is published.
_Avoid_: Master Data Hierarchy, a hierarchy inferred once and never documented

**Master Data Hierarchy**:
A chain of MDM relationships between master entities, such as parent and ultimate parent, each with its dates.
_Avoid_: Reference Hierarchy, a parent code

**Profiling Findings**:
The approved record of what a data set holds: each part's class, kind, key, identifiers, relationships, hierarchies, time model, sensitivity, quality defects and silver spec, with the evidence for each.
_Avoid_: A guess without evidence, an unapproved findings file used for onboarding

**Agent Context**:
The bounded, self-explaining answer an agent reads about an entity, code, relationship or silver table, carrying its definition, version, valid dates and provenance.
_Avoid_: A raw table dump, an answer without its version or source

### Snowflake operational roles

**Deployer Role**:
The account role that creates and owns Terraform-managed Snowflake infrastructure (warehouses, schemas, the dashboard Streamlit app) — deployment of infrastructure, not ownership of pipeline data objects.
_Avoid_: Owning the Gold views or the mirror, running dbt against Gold

**Managed Mirror**:
The one Snowflake copy of the data database's final tables (MDM, RDM and silver, as the schemas `MDM`, `RDM` and `SILVER`), kept current by Snowflake at its refresh interval. It carries only the tables the mirror record lists, and Snowflake owns its writes. Init makes it once the tables exist, before any load; a store reset removes it, and the next init makes it again.
_Avoid_: A copy written by the platform's own code, a mirror per store, mirroring working tables (the merge stage, reviews, lookups)

**Gold**:
The views in Snowflake that consumers read, written by dbt over the Managed Mirror by the Gold writer, the one identity that creates them. A Gold view reads only mirrored tables.
_Avoid_: Gold tables copied from the mirror without a measured need, Gold reading the stores directly

**Reader Role**:
The read-only consumption-layer role for dashboards and reports (the Streamlit-in-Snowflake dashboard runs as this role by Terraform pin; the standalone dashboard is bring-your-own-connection and not required to use it) — SELECT only, never owns or mutates pipeline objects.
_Avoid_: Granting write/ownership privileges, treating "dashboard" and "report" as distinct concepts (they are the same thing in this platform)

### Data plane (ingest and engagement)

**Canonical Silver**:
The `silver` schema of the data database, where each source's every detail lands typed and keyed, written by the silver writer. Snowflake reads it through the Managed Mirror.
_Avoid_: identity-refresh run snapshots, a second silver copy in Snowflake written by the platform

**VersionId Reclaim**:
Permanent removal of billed bytes on a versioned bucket by deleting specific `Key` + `VersionId` pairs. Key-only delete and `aws s3 rm` leave payloads billed behind delete markers.
_Avoid_: Recursive `s3 rm`, Terraform one-shot deletes, unversioned DELETE

**Accession Number**:
The number EDGAR gives one submission (one 10-K, one Form 4, one N-PORT report); an amendment gets its own. It has 18 digits in three parts, stored with dashes, as `0001234567-23-000123`: the submitter's ID (10 digits), the year (2) and a running count (6). The first part is the CIK of whoever sent the submission, often a filing agent, so it does not name the company the filing is about. The column is `accession_number`, SEC's own word; prose says "filing" where the number is not the point.
_Avoid_: filing ID (IAPD's `filing_id` is a different number), bare `accession` as a column name

**Derived Filing Text**:
A rebuildable normalized-text projection identified by Accession Number and interpretation version and produced from retained Bronze filing evidence; it is not source evidence.
_Avoid_: Bronze Artifact, raw filing, canonical source evidence

**Retirable Derived Filing Text**:
A Derived Filing Text identity outside the authoritative required set that has satisfied its deletion-eligibility boundary; this status never applies to the underlying Bronze evidence.
_Avoid_: Obsolete CIK, obsolete filing, Bronze deletion candidate

**Runtime System of Engagement**:
Silver warehouse state (typed tables after parse) is the authoritative published business state against which processors compute Lifecycle Diffs; the Change Ledger decides acquisition and processing eligibility and records completion.
_Avoid_: Silver as processing ledger, Bronze as business state, edgartools local disk cache as shared state, agent queries against silver

**Agent System of Engagement**:
Snowflake Decision Contract objects only; agents never read silver or bronze directly. A Mongo Decision Projection is not a second SoE.
_Avoid_: Runtime silver as agent API, ad-hoc SEC calls from the agent, Mongo as v1 SoE

**Human Explore System of Engagement**:
Labeled Explore Mode over Snowflake gold (and related analytics tables), not valid as Trading Decision input.
_Avoid_: Unlabeled explore as agent view

**SecGateway**:
The exclusive warehouse path for SEC network I/O, implemented with edgartools; every successful response eligible to affect warehouse state is captured as Bronze Persist evidence before processing.
_Avoid_: Parallel sec_client downloads for the same objects after cutover, parse paths that call SEC

**Verified-Evidence Acquisition Idempotency**:
Skip an SEC request only through a Change Ledger Fetch Decision backed by exact Verified Source Evidence, a sealed out-of-scope classification, or an operator exclusion; interpretation-version changes reprocess verified Bronze without redownloading.
_Avoid_: Silver row as download proof, S3 presence alone, parser upgrade as automatic refetch, worker cache decision

**Daily Identity Refresh**:
The recurring company-identity refresh for tracked entities whose recent SEC daily-index activity signals that their submissions state may have changed.
_Avoid_: Daily full-universe identity sweep, filing ingestion

**Find Companies To Check Today**:
The step that resolves which tracked companies belong in a Daily Identity Refresh's scope, by reading the trailing lookback window of SEC daily indexes for filing activity; it only builds that scope and does not itself re-fetch or re-resolve any company-identity data. Implemented as the `compute-identity-refresh-window` command / `FindCompaniesWithNewFilings` state.
_Avoid_: Treating this as the refresh itself (Daily Identity Refresh processes the scope this step produces), re-scanning the complete tracked universe (that is Identity Backstop Sweep's job), a data-mutating step

**Identity Backstop Sweep**:
The periodic refresh of company identity across the complete active company-eligible universe (`entity_type = operating` or present in the captured canonical SEC ticker snapshot), covering administrative submissions changes that have no filing signal.
_Avoid_: Daily identity refresh, historical filing backfill, MDM Reconciliation Backstop

**MDM Reconciliation Backstop**:
The periodic full-universe MDM match, survivorship, and relationship re-derivation pass that catches drift a bounded 1-hop incremental pass cannot see: multi-hop ripple, below-threshold near-misses, and skip-if-unchanged hash staleness.
_Avoid_: Identity Backstop Sweep, Daily Identity Refresh, Per-Type Exact Relationship Parity, mdm reconcile, limited mdm mastering

**Identity Refresh Slot**:
One scheduled opportunity to run either a Daily Identity Refresh or an Identity Backstop Sweep; it may be completed or deferred but never overlaps another identity refresh.
_Avoid_: Concurrent refresh trigger, untracked skipped schedule

**Overdue Identity Backstop**:
An Identity Backstop Sweep displaced by an active refresh and therefore prioritized at the next available Identity Refresh Slot.
_Avoid_: Silently skipped weekly sweep, narrow refresh taking priority

**Identity Refresh Batch Delta**:
The immutable, CIK-batch-scoped company-identity result produced within one Identity Refresh Run; it is not canonical silver and is eligible for consolidation only after its declared batch succeeds.
_Avoid_: Per-batch canonical publication, mutable shared batch output, treating a partial delta as a completed refresh

**Identity Refresh Reducer**:
The sole run-scoped publisher that verifies the complete Identity Refresh Batch Delta set, merges it with canonical silver, and performs the one ETag-guarded canonical promotion for that refresh run.
_Avoid_: Distributed canonical writers, canonical publish before complete-batch verification, bypassing the existing merge and promotion guard

**Identity Refresh Run**:
The immutable execution identity binding one selected CIK universe, one warehouse image and its declared batch deltas; complete verification of every declared batch is the run's gate (the reference snapshot and the canonical silver publication it once carried were retired with the DuckDB write path).
_Avoid_: Reusing successful deltas with changed inputs or image, retrying a failed batch as a new unbound refresh, publishing a partial run

**Identity Refresh Publication Retry**:
A bounded retry of only the Identity Refresh Reducer after an interrupted or ETag-conflicted promotion; it rehydrates canonical and re-merges the same verified Identity Refresh Run inputs without repeating batch capture.
_Avoid_: Re-running successful batches for a publication race, replacing run inputs during retry, unbounded silent retries

**Identity Refresh Aggregate Integrity**:
The reducer processes the declared batch-delta set in its manifest order and rejects any ambiguous same-key merge conflict, so no partial or arbitrarily resolved identity refresh can become canonical.
_Avoid_: Arrival-order merge, last-writer-wins conflict handling, publishing a subset after a rejected delta

**Bronze Persist**:
Mandatory immutable evidence of every successful source response eligible to affect warehouse state, recorded before its processing decision.
_Avoid_: Optional raw archive, changed-content-only capture, Bronze as processing-state authority

**Bronze Artifact**:
One immutable source byte sequence addressed by its canonical content identity; multiple Source Captures may reference the same artifact while retaining distinct observation provenance.
_Avoid_: Payload copy per poll, mutable latest object, request ID as content identity

**Temporary Bronze Stage**:
The new-enrichment-pipeline architecture's short-lived S3 landing location for exact source bytes while their hash, declared member inventory, and parser contract are verified. A complete publication remains until its Source Artifact Archive write is verified; a delta remains until every required consumer checkpoint and downstream verification passes, then is deleted without an archive copy. It is not durable processing authority or the long-term system of record. Existing SEC pipelines retain ADR 0006's durable Bronze contract until a separate migration is accepted.
_Avoid_: Applying this contract silently to existing SEC pipelines, archiving delta bytes, permanent hot Bronze storage for new enrichment, starting downstream work from an S3 listing, deleting a complete publication before archive verification, deleting a delta before required consumers and downstream checks pass

**Source Artifact Archive**:
The low-cost immutable S3 audit store for the latest verified complete source bytes of each new enrichment publication family after Temporary Bronze Stage verification; the Change Ledger records content identity, location, storage class, checksum parity, transition time, and every later physical storage transition. A verified accepted replacement permits authorized deletion of superseded bytes while permanent manifests, hashes, lineage, MDM Commit Evidence, and deletion evidence remain. Current-state replay and disaster recovery redownload the newest complete Source Publication and never wait for this archive.
_Avoid_: Retaining every superseded enrichment payload, deleting before replacement verification, S3 lifecycle age as deletion authority, archive restore as an operational dependency, checksum-only historical replay claim, untracked lifecycle transition, mutable latest object, archive state as processing authority

**Raw Evidence Hash**:
The digest of the exact source bytes that identifies one Bronze Artifact without claiming those bytes represent a business change.
_Avoid_: Domain hash, request identity, transport metadata as meaning

**Canonical Source Hash**:
A versioned digest of source content after removing transport-only representation differences but before interpreting it as business facts.
_Avoid_: Raw-byte equality as semantic equality, unversioned normalization, parsed-row hash

**Domain Content Hash**:
A versioned digest of the business meaning produced under one interpretation identity, excluding operational timestamps, attempts, paths, and serialization details.
_Avoid_: Ingest timestamp in change identity, run ID in business hash, raw artifact checksum as row meaning

**Lifecycle Diff**:
The business-key comparison between one complete interpreted source revision and the prior authoritative Silver publication, yielding changed or new upserts, scope-proved retirements, unchanged members, or explicit no-impact.
_Avoid_: Rewrite unchanged scope, byte-difference mutation, absence without Scope Completion

**Pinned Silver Publication**:
The exact authoritative Silver state against which a Lifecycle Diff is calculated; the Change Ledger records its identity and the resulting publication evidence without duplicating Silver row authority.
_Avoid_: Mutable latest during diff, PostgreSQL row copy as business authority, unpinned read

**Scope Publication Fence**:
The compare-and-swap guard requiring an overlapping Silver mutation to retain its Pinned Silver Publication as the current predecessor; disjoint scopes may publish concurrently.
_Avoid_: Last-writer-wins, stale diff commit, global Silver lock

**Bronze Evidence Retention**:
Every distinct Bronze Artifact is preserved indefinitely as replay and audit evidence; archival storage transitions are allowed, but deletion requires an explicit audited exception.
_Avoid_: Delete after processing, automatic retention expiry, duplicate-byte version accumulation

**Ledger Reinitialization**:
Restoration of local processing authority from a new complete Source Authority baseline beginning at the recovery point, without reconstructing lost historical ledger decisions.
_Avoid_: Infer old decisions from Bronze, pretend historical continuity, resume from an unverified partial baseline

**Initial Ledger Bootstrap**:
The first production Ledger Epoch established through the same authorized Hybrid Source Baseline, catch-up, verification, and cutover path used for later reinitialization.
_Avoid_: Import legacy checkpoints as authority, incremental start without baseline, separate untested bootstrap semantics

**Reinitialization Authorization**:
The explicit audited decision to create a new Ledger Epoch, naming its reason, baseline cutoff, source-family coverage contract, deployment cohort, and authority identity before recovery work begins.
_Avoid_: Automatic empty-ledger rebuild, implicit epoch creation, activation without evidence

**Hybrid Source Baseline**:
The complete starting state for a new ledger epoch, combining closed Source Authority change intervals with fresh complete snapshots for every source family lacking complete change capture.
_Avoid_: Filing-index-only recovery, stale Bronze inventory as current proof, ready with uncovered source family

**Baseline Coverage Contract**:
The sealed set of required source families and their accepted completeness proofs for a Ledger Epoch; every required family must complete before authority may activate.
_Avoid_: Partial baseline activation, automatic failure exclusion, unlisted required source

**Source Family Registry**:
The versioned authority contract naming each source family's logical keys, acquisition method, completeness proof, poll or change-discovery policy, and required Silver producers; an affected required family cannot activate under a new version without scoped baseline and catch-up evidence.
_Avoid_: Deployment-defined completeness, undocumented source addition, producer set inferred at runtime

**Registry Transition**:
A bounded change to a healthy epoch's Source Family Registry with an explicit effective boundary, affected-family baseline, catch-up, and activation gate; a new Ledger Epoch is reserved for initialization or lost ledger authority.
_Avoid_: Full epoch rebuild for every source change, deploy-time registry mutation, mixed registry versions without a boundary

**Baseline Catch-up Barrier**:
Proof that every source family covers its Hybrid Source Baseline through the sealed activation high-water mark, using a final complete snapshot wherever change capture is incomplete.
_Avoid_: Activate then catch up, rebuild acquisition blackout, unclosed baseline gap

**Ledger Epoch**:
One continuous period of local processing authority beginning at a verified Hybrid Source Baseline; evidence from earlier epochs remains historical unless explicitly selected for backfill, repair, or reprocessing.
_Avoid_: Inferred pending work across reinitialization, hidden epoch reset, historical Bronze automatically queued

**Environment Authority Boundary**:
The rule that fetch decisions, observations, Bronze evidence bindings, processing decisions, and epochs belong to one environment and account; external evidence requires an explicit checksum-verified operator import that creates local lineage.
_Avoid_: Dev capture satisfying production implicitly, shared mutable acquisition state, cross-account artifact reference without import authority

**Silver Baseline Candidate**:
A complete, non-serving Silver state rebuilt from one Hybrid Source Baseline to establish a new Ledger Epoch, activated only after its coverage, counts, and content are verified.
_Avoid_: Trust existing Silver after ledger loss, patch an unexplained state, serve the rebuilding candidate

**Immutable Source Conflict**:
Contradictory Bronze Artifacts observed under one immutable source identity; all evidence is retained and the source key is quarantined until an explicit repair decision resolves processing authority.
_Avoid_: First-writer-wins, latest-writer-wins, overwrite contradictory evidence

**Repair Revision**:
An immutable child revision that records which quarantined evidence may drive processing, which evidence was rejected, and the reason and authority for superseding the original conflict.
_Avoid_: Amend quarantined revision, delete rejected evidence, invisible operator correction

**Logical Source Revision**:
A verified source observation materialized after Source Capture, binding its reserved monotonic per-key position to canonical content and interpretation identities.
_Avoid_: Revision before evidence, consumer completion order, S3 arrival time as ordering, Bronze object path as business identity

**Source Observation Position**:
The monotonic per-key order reserved by a Source Fetch Decision before transport; not-modified, skipped, or failed attempts may leave unused positions without creating Logical Source Revisions.
_Avoid_: Dense revision requirement, response-arrival order, renumbering after retry

**Source Change**:
The transport-independent selection of a Logical Source Revision for a Change Propagation Run, carrying the Bronze Persist evidence reference for its source observation.
_Avoid_: Bronze object as the change itself, queue delivery as business identity, parser output row as source identity

**Change Ledger**:
The sole local authoritative record of each Logical Source Revision's processing disposition and progress; immutable source artifacts are evidence referenced by it, not competing control state.
_Avoid_: Bronze as processing-state authority, S3 listing as consumption state, dual authority

**Ledger State Record**:
The atomic pairing of constrained current state with immutable within-epoch transitions, attempts, outcomes, and reasons for one ledger-controlled lifecycle.
_Avoid_: Mutable status only, unconstrained event sourcing, current state without transition evidence

**Source Change Status**:
The Change Ledger's unified operator-facing projection for each discovered source candidate, showing its cause, fetch decision and state, Bronze evidence, logical revision, processing state, expected-producer progress, current blocker, and next action while immutable transition records remain the audit trail.
_Avoid_: Raw-table interpretation by operators, log-derived status, separate download and processing dashboards with conflicting truth

**Transition Ownership**:
The rule that each Change Ledger transition family has one authorized role, preventing workers from certifying their own publications or altering operator authority.
_Avoid_: Shared writer role, self-approved output, coordinator as universal database proxy

**Source Authority**:
The external publisher whose current source material defines what the platform may truthfully capture; for SEC-family data this is SEC or its designated source system.
_Avoid_: Bronze as original publisher, Change Ledger as source-content authority, downstream table as source truth

**MDM Enrichment Program**:
The governed portfolio that adds source-grained external evidence to MDM through independently releasable domain consumers. It includes GLEIF and separately governed non-GLEIF sources without turning one source, consumer, or release into authority for another.
_Avoid_: Monolithic enrichment pipeline, one big-bang release, inclusion as production authorization, mixing source authority across domains

**MDM Enrichment Consumer**:
An independently releasable projection of accepted external evidence into one supported MDM entity or relationship domain, with its own completeness, correctness, replay, rollback, and observability gates.
_Avoid_: Generic all-entity consumer, shared release fate, source capture as automatic publication

**Conditional Enrichment Source**:
An enrichment source represented in the program but not authorized for implementation until its authority, license, coverage, cost, cadence, and usefulness gates pass.
_Avoid_: Roadmap inclusion as ingestion approval, unlicensed production feed, implied mandatory delivery

**Deferred Domain Evidence**:
Captured external evidence whose semantics belong to an MDM domain that has no supported consumer or accepted local identity yet; it remains auditable and nonpublishing until that domain resolves it.
_Avoid_: Generic placeholder entity, coercion into Company, dropped unsupported record

**Enrichment Stewardship Decision**:
An immutable, evidence-and-run-bound human resolution of an identity link, field conflict, relationship endpoint, or identifier-mapping conflict. It may authorize a source projection but never silently merges MDM entities.
_Avoid_: Log-only review, mutable decision row, review acceptance as entity merge

**Fetch Planner**:
The acquisition actor that decides which source files to get and records that as a Change Ledger Fetch Decision; it never downloads or verifies bytes itself.
_Avoid_: Worker that plans its own work, fetch without a recorded decision

**Source Capturer**:
The acquisition actor that downloads one source file, verifies its hash, and records the capture as Bronze Persist evidence; it never decides what to fetch or what the bytes mean.
_Avoid_: Capture as processing, unverified download recorded as evidence

**Revision Claimer**:
The acquisition actor that marks one verified Logical Source Revision as being processed so it is processed exactly once; it seals what the revision requires without producing outputs.
_Avoid_: Processing without a claim, two claimers on one revision

**Publication Verifier**:
The file-grained acquisition actor that records whether a Source Publication's declared members are all captured, verified, and produced, or failed; a consumer may start only after it records complete. It knows nothing about entities.
_Avoid_: Pre-merge candidate review, entity matching, partial publication recorded as complete

**Ledger Repairer**:
The human-driven acquisition actor for quarantine, exclusion, and superseded-artifact deletion evidence in the Change Ledger; the physical deletion is an infrastructure permission, not a ledger role.
_Avoid_: Routine pipeline writes, silent repair without evidence

**MDM Committer**:
The single path that writes MDM master tables: one atomic bounded batch holding decisions, projection, MDM Commit Evidence, Consumer Checkpoint, and publication intents, or nothing. Applications hold no direct master-table write.
_Avoid_: Direct table write, partial batch, nested commit

**MDM Commit Evidence**:
The durable entity-change and relationship-version facts one Bookkeeping run committed to MDM, used to count that run's committed outputs by type; a later change or export does not replace the run that originated them.
_Avoid_: Full processing funnel, current-row last modifier, a log window

**Steward**:
The person or deterministic rule recorded as the actor of an Enrichment Stewardship Decision; an attribute of the decision, not a database role.
_Avoid_: Separate database role, decision without a named actor

**Adjudicated Seed Link**:
A previously reviewed external-identity link imported with its complete decision evidence and revalidated against the current source baseline and uniqueness rules before publication.
_Avoid_: Trusted static mapping, population-wide auto-link rule, unvalidated historical approval

**Enrichment Business Retirement**:
The evidence-backed closure of a current enrichment link, projection, mapping, or relationship while preserving its historical versions and decisions. It requires an explicit source change or complete reconciliation; a partial delta's absence cannot retire evidence.
_Avoid_: Physical deletion, absence-as-retirement, silent successor rebinding

**Enrichment Evidence Retention**:
Permanent preservation of Normalized Source Evidence, Change Ledger and Bookkeeping history, stewardship decisions, temporal MDM history, manifests, hashes, run lineage, MDM Commit Evidence, and deletion records independently from deletion of superseded raw source bytes.
_Avoid_: Treating never looking back as permission to erase control or MDM history, keeping every byte forever, deleting audit lineage with raw files, key-only S3 deletion

**Enrichment Planning Complete**:
The state in which every mandatory and conditional enrichment workstream has an explicit destination, dependencies, authority, evidence requirements, release gates, and terminal outcome path, with no hidden design decision.
_Avoid_: Implementation complete, ticket list without decisions, roadmap as source approval

**Enrichment Program Complete**:
The state in which every mandatory enrichment consumer has production-bound evidence and every conditional source has either shipped through its gates or reached a documented defer-or-reject outcome with an objective review trigger.
_Avoid_: Every investigated feed must ship, unresolved conditional research, one global big-bang release

**Conditional Source Decision**:
The evidence-backed `adopt`, trigger-bound `defer`, or reasoned `reject` outcome for a Conditional Enrichment Source after authority, license, coverage, value, identity safety, cadence, cost, replay, retention, and domain ownership are evaluated.
_Avoid_: Indefinite investigation, access as approval, undocumented rejection

**Company Legal-Entity Enrichment**:
Additive legal identity, lifecycle, registration, and accounting-consolidation evidence for a Company from GLEIF. SEC remains the Source Authority for SEC filings and reported financials; GLEIF is the Source Authority for the published Global LEI Index evidence. Company MDM preserves both sources in one master view without turning GLEIF evidence into SEC evidence.
_Avoid_: GLEIF as a financial-statement source, replacing CIK with LEI, collapsing accounting consolidation into generic ownership, mixing Fund or Branch records into Company MDM

**GLEIF Daily Delta Refresh**:
The once-daily capture and application of the 24-hour GLEIF Golden Copy deltas. It advances source evidence for changed LEIs, relationships, and reporting exceptions without rematching the complete MDM universe.
_Avoid_: Three-times-daily polling, downloading a full Golden Copy every day, full-universe matching after every delta

**GLEIF Evidence Capture**:
The shared source evidence for all GLEIF Level 1 entities, Level 2 relationships, and reporting exceptions. Each MDM domain consumes only records whose entity and relationship semantics belong to that domain.
_Avoid_: Filtering source capture to SEC companies, putting every LEI into Company MDM, downloading the same GLEIF publication separately for each domain

**Enrichment Source Publication**:
One immutable native release from an enrichment Source Authority, identified by its publication identity, time, declared artifact inventory, hashes, source contract, and capture run. Linked file families may keep independent checkpoints while a consumer advances only after all of its required families are verified.
_Avoid_: Filename as publication identity, mutable latest URL as evidence, one file silently standing for a multi-file release, equivalent XML/JSON/CSV encodings treated as separate business releases

**Enrichment Publication Artifact**:
One declared source archive within an Enrichment Source Publication, verified in the Temporary Bronze Stage with its archive hash, expected member inventory, source format, parser contract, observed record count, and Change Ledger transition history. The latest complete publication is retained in the Source Artifact Archive; delta bytes are deleted after every required consumer and downstream verification passes.
_Avoid_: Extracted temporary file as source authority, undocumented side file, parser output as raw evidence, duplicate capture per MDM domain

**GLEIF Candidate Backstop**:
The weekly re-evaluation of unresolved, unmatched, newly eligible, or materially changed MDM entities against current captured GLEIF evidence.
_Avoid_: Daily full-universe rematch, treating no candidate as a permanent no-LEI finding

**GLEIF Full Reconciliation**:
The monthly comparison of the complete captured GLEIF Golden Copy with all in-scope MDM enrichment state, including records missed or retired across delta processing.
_Avoid_: Daily full-snapshot load, delta-only authority without periodic completeness proof

**Ledger-Gated Acquisition**:
No new source request may begin while the Change Ledger is unavailable; evidence from an already authorized in-flight request remains unprocessable until its original ledger lineage is reconciled.
_Avoid_: Local decision spool, Bronze fallback authority, ungated outage download

**Source Fetch Decision**:
The Change Ledger's required authorization or explicit skip decision for one source network request, recorded before any request is attempted and carrying the reason it may or may not proceed.
_Avoid_: Ungated SEC request, post-facto download audit, implicit skip

**Source-Key Fetch Ownership**:
Exclusive authority for one active source request against a logical source key; independent keys retain parallel fetch ownership.
_Avoid_: Same-key concurrent download, global fetch lock, deduplicate after racing SEC calls

**Fetch Attempt**:
One fenced execution of a Source Fetch Decision; a retry creates a new attempt while preserving the original cause, source position, request identity, and conditional validators.
_Avoid_: New source observation per retry, reused fencing token, racing finalization

**Fetch Cause**:
The immutable reason a Source Fetch Decision exists: a captured source discovery observation, a versioned poll policy, or an explicit operator repair, backfill, or reprocess request.
_Avoid_: Unexplained schedule trigger, worker-invented URL, missing causal lineage

**Poll Policy**:
The versioned Change Ledger rule for a source without complete change discovery, recording its last completed observation, next eligible time, conditional validators, and reason; a scheduler may request work, but only a due ledger decision authorizes the source call.
_Avoid_: Scheduler-owned acquisition truth, worker cache-age decision, post-facto poll authorization

**Discovery Manifest**:
The immutable, counted, and digested candidate set derived from one complete source discovery observation; every candidate must receive an explicit Fetch Decision before its interval closes.
_Avoid_: Downloaded-items-only inventory, omitted candidate as skip, workflow count as completeness

**Open Discovery Interval**:
A discovery interval with at least one required candidate still deferred or otherwise non-terminal; it remains incomplete, ages visibly, and cannot satisfy a baseline or catch-up barrier.
_Avoid_: Close with deferred candidate, timeout-to-skip, hidden coverage gap

**Acquisition Universe**:
The sealed, versioned set of source families, source keys, forms, and history boundaries for which source coverage and child-download decisions are authoritative.
_Avoid_: Entire SEC by implication, mutable tracking table as scope, unversioned command filter

**Universe Transition**:
A versioned Acquisition Universe change: additions require a complete scoped baseline, while removals end future coverage without rewriting or retiring Source Authority facts.
_Avoid_: Tracking-table-only change, delete facts on removal, incremental processing before added-key baseline

**Download Disposition**:
The explicit classification separating a terminal reason not to fetch, a temporary deferral, and the outcome of a request that was actually attempted.
_Avoid_: Generic skipped, rate-limit skip, treating not-modified as no request

**Not-Modified Observation**:
Evidence that an authorized source check found no new producer revision or content, linked to the prior Source Capture without creating new Bronze bytes or processing work.
_Avoid_: New source revision for every poll, invisible 304, no-impact Silver publication for an unchanged fetch

**Missing Source Artifact**:
An expected source candidate whose authorized fetch cannot obtain its artifact; it remains retryable or quarantined and never proves deletion or retirement by itself.
_Avoid_: 404 as retirement, not-found skip, close discovery interval without evidence

**Failed Source Response**:
A non-success source response retained as Fetch Attempt evidence with status, headers, timing, retry classification, and any diagnostic body reference; it creates neither a Bronze Artifact nor a Logical Source Revision.
_Avoid_: Error page as Bronze source data, 404 as source revision, logs as the only retry evidence

**Source Capture**:
A source response is durably acquired only when its immutable Bronze Persist evidence is verified and the exact evidence reference is finalized in the Change Ledger.
_Avoid_: Downloaded on network receipt, unverified upload success, untracked Bronze object

**Verified Source Evidence**:
The Change Ledger binding between an exact source identity, canonical checksum, terminal Source Capture, and verified Bronze Artifact required to prove that source need not be downloaded again.
_Avoid_: S3 path existence, Silver row as download proof, unverified artifact reference

**Orphaned Capture**:
Verified Bronze evidence whose authorized fetch was not finalized in the Change Ledger; it may be reconciled only to that pre-existing Fetch Decision, otherwise it remains quarantined.
_Avoid_: S3-created ledger authority, delete-and-forget evidence, attach to a different request

**Processing Decision**:
The Change Ledger's classification of a Source Capture using both its logical content identity and its interpretation identity, determining whether processing is required or explicitly has no impact.
_Avoid_: Checksum-only skip, parser-blind deduplication, implicit no-op

**Interpretation Reprocess**:
New processing work over existing Verified Source Evidence caused by a changed parser, schema, contract, or configuration identity, without requiring a new source observation.
_Avoid_: Redownload for parser change, mutate prior interpretation, worker-selected evidence

**Processing Disposition**:
The explicit, reasoned classification of a captured revision as processing-required, no-impact, out-of-scope, operator-excluded, superseded, quarantined, retryable-failure, or processed.
_Avoid_: Generic process-skipped, free-text-only outcome, silence as success

**Processed Source Revision**:
A Logical Source Revision backed by a verified Silver publication or verified no-impact publication whose identity, counts, and digest are finalized in the Change Ledger.
_Avoid_: Parser success, landing upload, task success, workflow success

**Expected Producer Set**:
The sealed set of Silver producers, tables, and scopes that must each publish a verified outcome for one Logical Source Revision before it is processed.
_Avoid_: Infer expected output after execution, silence as no-impact, first-producer success as complete

**Source Lifecycle**:
The two independent Change Ledger histories for one source observation: its fetch decision and outcome, and its processing decision and outcome.
_Avoid_: Combined download-processing status, generic skipped, inference from workflow history

**Ordered Revision Queue**:
The per-key sequence of captured Logical Source Revisions awaiting processing; capture may advance, but a later revision cannot publish or become current before every earlier position has a terminal processing disposition.
_Avoid_: Fetch blocked by Silver completion, later-writer-wins, global processing order

**Gap Closure**:
An explicit exclusion or supersession that unblocks a later source position without claiming the closed revision was processed or advancing the cursor by itself.
_Avoid_: Exclusion as no-impact, partial publication activation, permanently poisoned key

**Complete-Snapshot Supersession**:
Automatic replacement of an earlier incomplete or quarantined mutable-snapshot revision by a newer revision that proves complete authority over the same replacement scope, with explicit ledger linkage.
_Avoid_: Partial newer snapshot wins, immutable filing supersession, unrecorded latest-wins

**Snapshot Coalescing Policy**:
The versioned source-family rule declaring whether multiple complete queued snapshots preserve distinct semantic history or may collapse to the latest complete state before processing.
_Avoid_: Universal latest-wins, worker-selected coalescing, coalesce immutable observations

**Coalescing Boundary**:
The point before any Silver producer publication commits for an older complete snapshot; coalescing is forbidden after this boundary.
_Avoid_: Coalesce partial publication, coalescing as rollback, stranded producer output

**Scope Completion**:
Proof that one Logical Source Revision authoritatively enumerates an entire replacement scope, including a valid scope with zero members.
_Avoid_: Missing output as empty scope, partial parse as complete, physical deletion as retirement proof

**Silver Landing Retirement Record**:
The explicit, append-only signal that a business key present in an earlier complete scope is absent from a newer Scope Completion for the same source family; written directly by the source family's own acquisition code into a shared landing companion relation the moment it proves the shrink, never inferred downstream from a missing row's absence.
_Avoid_: Absence-as-retirement, per-table bespoke retirement columns, inferring retirement at query/refresh time from what a collapse query didn't see

**Change Propagation Run**:
The immutable unit that binds one selected set of new, modified, or retired source facts to its parser/schema versions, Affected-Key Closure, expected producers, stage outcomes, and aligned publication watermarks.
_Avoid_: Mutable run ID, full-universe refresh, unbound retry, distributed transaction

**Affected-Key Closure**:
The smallest set of source keys, business keys, and derived dependents that must be recomputed for a Change Propagation Run to converge correctly without processing unrelated data.
_Avoid_: Literal changed rows only, full-universe recomputation, best-effort dependency selection

**Daily-Artifact Run Manifest**:
The immutable, ordered filing selection for one daily-artifact run, bound to its daily-index input identity, warehouse image, and parser/configuration versions; it is the only candidate set a resume may use.
_Avoid_: Re-selecting candidates on retry, mixing image or index inputs, adding repaired work through a later run's selection

**Daily-Artifact Outcome Ledger**:
The append-only, run-and-filing-scoped record of candidate attempts and dispositions. Successful work is final; only pending, retryable, or explicitly repair-authorized work may be resumed.
_Avoid_: Process-local telemetry as recovery state, overwriting failures, full-task rework after a partial success

**Daily-Artifact Repair Attestation**:
An immutable operator record that binds an immutable-content conflict, checksum evidence, repair action, and operator identity to one original manifest candidate before its bounded replay. It does not override the immutable-object guard.
_Avoid_: Accepting a mismatch silently, replacing an object without evidence, treating a new selection as repair

**Reported Executive Employment**:
The `EMPLOYED_BY` scope evidenced by SEC proxy disclosure and Form 8-K Item 5.02 events for named executives or covered officers; it does not represent every employee of an issuer.
_Avoid_: Company workforce, compensation row as timeless employment, officer event without temporal effect

### Agent decision support

**Agent Decision Surface**:
The versioned, machine-readable set of SEC-derived facts and features an automated trading agent may read when forming a trading decision; humans may audit the same surface, but charts and dashboards are not the contract.
_Avoid_: Streamlit app as source of truth, research notebook export, ad-hoc SQL without a published contract, trading execution API

**Semantic View**:
A person-certified Explore-only question contract for one Gold fact grain: its dimensions, its joins, its facts, and the metrics over that grain. Descriptions and synonyms are words on those objects, not a fifth object. Certifying the view does not bind it into the Agent Decision Surface.
_Avoid_: A physical denormalized table, a query against Silver, a view that mixes fact grains, an uncertified model, a free Gold join treated as what an agent saw

**Dimension**:
A gold-approved MDM master attribute or RDM code meaning used to group or filter one Semantic View. An RDM Dimension names its approved code-set version.
_Avoid_: A copied master field on the fact table, a Silver column, a metric

**Fact**:
A row-level amount, quantity, date, or link key on the one Gold fact table of a Semantic View.
_Avoid_: An MDM or RDM field repeated as a fact, a Silver row, a metric

**Metric**:
A named aggregation over one Semantic View's facts, at that view's grain.
_Avoid_: A row-level fact, an unqualified sum, a second business definition

**Verified Query**:
A question and its SQL for one Semantic View. An example is the question before that pair is accepted.
_Avoid_: The answer rows, a metric, a second business definition

**Join**:
The fact grain's named link to one Dimension inside a Semantic View. Two Joins may reach the same Dimension when each names a different role. A Join must not multiply the grain, and it uses the time scope that Gold fact table already declares. An MDM relationship may be the evidence for it, but it is a different object.
_Avoid_: Semantic Relationship, Relationship Interval, Relationship Applicability, a name match, an unapproved join

**Decision Feature**:
A named, typed field on the Agent Decision Surface with documented meaning, null semantics (unknown vs zero), and identity keys (for example CIK and fiscal period).
_Avoid_: Chart series, dashboard metric, unexplained column

**Trading Decision**:
An action choice formed by an agent *outside* this platform’s execution boundary (for example buy, sell, hold, size, or abstain); this platform supplies decision inputs, not order placement or portfolio management.
_Avoid_: Broker order, fill, portfolio rebalance inside the warehouse

**Human Audit View**:
A read-only UI (for example Streamlit-in-Snowflake) that shows the same facts available on the Agent Decision Surface so a person can verify what an agent would have seen. The same Bundle Subject (CIK) may stay selected when switching Agent View Mode and Explore Mode in one session.
_Avoid_: Primary product surface, customer research portal, operator release console, clearing the company on every mode switch

**Agent View Mode**:
A Human Audit View mode that renders only issuer Snowflake Decision Contract objects (feature screen, issuer bundle, contract status, display status, subject resolver) so a person can see what the agent is allowed to read at a Decision Watermark. When the contract is not READY, it shows a display not-ready reason; ready views stay empty.
_Avoid_: Mixing unlabeled explore queries into agent view, calling free gold joins "what the agent saw", manager bundle or standalone holders/auditor views as Agent View, falling back to gold inside Agent View when not READY

**Explore Mode**:
A Human Audit View mode that may query gold (and related) tables beyond the Decision Contract for human investigation; it is not an input to Trading Decisions and must show a persistent banner that it is not the Snowflake Decision Contract. The Agent View allowlist, not the banner, blocks gold in Agent View Mode.
_Avoid_: Using explore as the agent source of truth, silent mode switching, explore without "not agent contract" labeling, treating the banner as the only control

**Decision Graph Bundle**:
The Agent Decision Surface unit of read: a multi-entity payload rooted at one subject (usually an issuer) that includes related entities and relationship edges the agent may use, bound to one Relationship Generation Snapshot / data watermark.
_Avoid_: Single-table company row, ad-hoc multi-query join by the agent, unbounded "whole graph" dump, Streamlit ego-network screenshot

**Current-at-Watermark Relationship**:
A relationship version whose proven date interval contains the as-of date under `[valid_from_date, valid_to_date)` semantics; a relationship with an unknown interval is kept but is not current for a strict as-of read.
_Avoid_: Unknown-date-as-current, timestamp-inclusive end date

**Bundle Subject**:
The primary entity the Decision Graph Bundle is built for (typically a company identified by CIK); related persons, advisers, funds, securities, and edges are included only as they attach to that subject under declared relationship types and applicability rules.
_Avoid_: Portfolio of tickers as one bundle, anonymous search result set

**Trading-Relevant Neighborhood**:
The v1 Decision Graph Bundle scope around a Bundle Subject. Agent-grade sections are As-Of Decision Features, current `IS_INSIDER` edges, and current `EMPLOYED_BY` edges. Institutional holders, auditor, and parent keys remain on the payload but are not v1 Trading Decision input until their gold/graph bind exists; ADV is `not_applicable` for a pure issuer.
_Avoid_: Full MDM type registry dump, ADV-first bundle, treating unbound 13F gold or zero-row auditor/parent evidence as agent-grade, every historical edge without currency rules

**v1 Agent-Grade Input Facts**:
The Snowflake gold rows and active-graph edges that v1 Trading-Relevant Neighborhood sections read, before the Snowflake Decision Contract publishes them: As-Of Decision Features from `FINANCIAL_FACTORS`, current `IS_INSIDER` edges, and current `EMPLOYED_BY` edges.
_Avoid_: Decision Contract views as a substitute for missing gold or graph columns, treating locked-unavailable neighborhood keys as v1 input work, agents reading silver or bronze

**Current Neighborhood (default)**:
The Decision Graph Bundle edge set limited to Current-at-Watermark Relationships for the declared business date; ended or not-yet-current edges are omitted unless the consumer explicitly requests history.
_Avoid_: All generation-eligible edges as default, silent inclusion of former insiders as current

**Neighborhood History (optional)**:
Generation-Eligible Relationship Versions that are not current at the watermark, returned only when requested, each carrying temporal fields and an explicit not-current marker so agents cannot treat them as live.
_Avoid_: Default payload, history without valid_from/valid_to, mixing current and historical without flags

**As-Of Decision Features**:
Subject-level Decision Features published for the Bundle Subject at the bundle watermark: a primary annual vector plus an optional latest interim if newer; interim does not require FY. Coverage is present / empty / unavailable for FY and present / not_applicable for interim; all-null measures are empty, not unavailable. Values must be the latest complete computation available for that as-of (not a stale prior export). Null is not zero.
_Avoid_: Shipping last week's factor file, treating null CAGR as zero, requiring the agent to recompute CAGR from raw facts for v1, conflating "uses historic inputs" with "may be stale"

**Primary Annual Feature Vector**:
The As-Of Decision Features taken from the most recent complete fiscal-year (FY) factor row available for the Bundle Subject at the watermark.
_Avoid_: Mixing FY and quarter metrics without labels, oldest FY, average of all years

**Latest Interim Feature Vector**:
When a non-FY fiscal period exists with period_end after the Primary Annual Feature Vector's period_end (or after nothing, if there is no FY), its factor row is included alongside the annual vector and explicitly labeled as interim; otherwise the interim section is `not_applicable`.
_Avoid_: Replacing FY with Q silently, inventing interim when none is newer than FY, requiring FY before an interim may be present

**Snowflake Decision Contract**:
The v1 delivery of the Agent Decision Surface: published Snowflake objects (views, tables, or procedures) that return Decision Graph Bundles or their relational equivalent under a declared schema version; the Human Audit View queries these same objects. Bootstrap SQL owns the `EDGARTOOLS_DECISION` objects; dbt owns gold and silver; Python owns semantics; the watermark aggregator writes READY.
_Avoid_: Streamlit-only data path, agent-private tables that diverge from audit UI, S3 file dump as the primary contract, undocumented ad-hoc gold joins, dbt-owned READY publication, treating Mongo as the v1 contract

**Mongo Decision Projection**:
An additive public-internet copy of a READY Snowflake Decision Contract onto MongoDB documents for v2 agents. It is not a second Agent System of Engagement. A separate publisher writes it after READY. It publishes one issuer Decision Graph Bundle document per Bundle Subject (same section envelope; holders, auditor, and parent stay unavailable; ADV is not_applicable) and one Subject Feature Screen document per Bundle Subject. Each agent-grade document carries the full Decision Watermark required for an Agent-Grade Read, including bronze identity when bronze persist was used, plus an explicit READY marker. If the projection does not match current READY Snowflake, the publisher fail-closes in place (`not_ready`, not agent-grade) without deleting the payload; the v2 agent abstains.
_Avoid_: Mongo as v1 SoE, parallel gold/graph writer, Python bundle dump without READY, Mongo winning when Snowflake disagrees, four-field pin as the full watermark, warehouse ingest into Atlas, one universe Feature Screen document, Explore gold as v2, omitting bundle sections silently, paid Atlas as a v2 prerequisite, private-only Atlas as the v2 agent path, watermark aggregator as the Mongo writer, deleting projection docs on pointer move

**Decision Watermark**:
The composite identity bound into every Decision Graph Bundle as inspectable components: a digest of the ordered unique content-addressed Bronze artifact hashes (mandatory; the full hash list is not the watermark), silver-derived parse/completeness claims (versions and section coverage), Relationship Generation Snapshot / active graph generation id, gold/feature as-of (run_id), and business date; a bundle is invalid for agent use if any required component is missing or the components are known to disagree. A concatenated display token may exist for logs, but it is not the identity.
_Avoid_: Persist-only bronze hash, capture-manifest id as the bronze identity, ledger revision as the bronze identity, listing every Bronze artifact hash on the contract row, concatenated watermark string as the identity, wall-clock now, best-effort multi-table join without pins, gold-only or graph-only as sole identity

**Pure-SEC Decision Features**:
Decision Features derived only from SEC (and approved operator-supplied SEC-family) filings and platform calculations on those filings; market prices, market cap, and price-derived multiples are outside the Agent Decision Surface.
_Avoid_: PE, EV/EBITDA from prices, yfinance fields inside the bundle, silent nulls that look like "no market data loaded" mixed with accounting nulls without a separate market contract

**Warehouse-Active**:
A company whose warehouse sync tracking status is `active` (past first bootstrap, not pending, not deregistered). This is warehouse tracking, not gold `COMPANY.tracking_status`, which is an MDM column.
_Avoid_: bootstrap_pending as warehouse-active, gold COMPANY.tracking_status as warehouse-active, silver sec_company existence as tracking

**Decision Subject Universe**:
The set of Bundle Subjects eligible for agent consumption: the intersection of warehouse-active and MDM-active entities, published as a watermark-aligned snapshot on the Snowflake Decision Contract. One-sided CIKs are excluded; an empty intersection is not a publishable contract.
_Avoid_: MDM-only tracking_status, gold COMPANY.tracking_status as the warehouse-active flag, warehouse-only COMPANY rows, listing one-sided CIKs as unavailable agent subjects, live join to bookkeeping as the agent universe, ad-hoc one-off CIKs without tracking, investable cohort unless explicitly adopted later

**Bundle Coverage Flags**:
Structured present / empty / unavailable / not_applicable markers on each section of a Decision Graph Bundle so partial data is explicit; empty means complete derivation with zero members, unavailable means the platform could not assert completeness for that section at the Decision Watermark. v1 keeps holders, auditor, and parent keys as unavailable (missing bind or inventory), not empty.
_Avoid_: Omitting sections silently, zeros that mean "unknown", calling zero-row auditor/parent evidence empty, attaching unbound gold 13F as agent-grade, hard-failing the whole bundle for one missing optional section

**Decision Contract Version**:
An explicit integer (or major.minor) schema identity carried on every Decision Graph Bundle and Snowflake Decision Contract response; agents pin a supported version. The first published Snowflake Decision Contract is version 1. Breaking shape or semantics changes after a READY publication require a version bump.
_Avoid_: Docs-only changelog, watermark-only identity for shape, silent column renames, calling the first live publication version 2 because an unpublished sketch existed

**Latest Complete Holdings Period**:
For institutional/13F-style holdings in a Decision Graph Bundle, the most recent report period that is fully loaded for the relevant managers/subject at the Decision Watermark; the section is still "current" under Current Neighborhood rules only relative to that lagged source period, and coverage metadata must expose the period and known reporting lag—not same-day market positions.
_Avoid_: Intraday holdings, treating missing 13F as zero position without unavailable, shipping all historical 13F periods in the default neighborhood

**Subject Feature Screen**:
A flat, Decision Watermark–aligned relation over the Decision Subject Universe of As-Of Decision Features (Primary Annual and optional Latest Interim labels) used to rank or filter many subjects without loading full Decision Graph Bundles.
_Avoid_: Full neighborhood in the screen, free gold joins labeled as the screen, screen without Decision Contract Version / watermark

**Subject Bundle Read**:
The single-subject retrieval of a Decision Graph Bundle (Trading-Relevant Neighborhood + features + coverage + watermark + contract version) for deep agent inspection before a Trading Decision.
_Avoid_: Requiring full-universe dump to inspect one CIK

**Deferred Access Control**:
v1 of the Agent Decision Surface does not implement product-level authentication (for example OAuth); access is whatever the operator's Snowflake (or equivalent) session already allows. v2 internet agents use one read-only Atlas database user (SCRAM) plus TLS; the Mongo publisher uses a separate write user. The contract must remain callable behind a later pluggable access layer without changing Decision Feature semantics or bundle shape.
_Avoid_: Baking a one-off auth scheme into the bundle schema, blocking go-live on OAuth, assuming public internet exposure of Snowflake, sharing the publisher write user with internet agents, treating Atlas UI / plugin OAuth as trading-agent auth

**Agent-Grade Read**:
A Subject Bundle Read or Subject Feature Screen result whose Decision Watermark components are present and aligned, including the Bronze digest, over a non-empty Decision Subject Universe; only Agent-Grade Reads are valid inputs to a Trading Decision. Missing bronze digest or empty universe is not READY and not agent-grade (no tradeable payload). An empty or unavailable neighborhood section does not by itself fail the bundle. If the active graph generation changes, agent-grade reads fail closed; the old READY publication is not rewritten.
_Avoid_: Best-effort mismatched graph and features, silent degraded data for trading, READY publication without bronze digest, READY publication of an empty universe, serving a retired graph generation as agent-grade, failing a bundle because one issuer has no insiders, treating missing bronze as coverage-only, failing gold or MDM because the contract is not READY, "prefer gold" or "prefer graph" without invalidation

**Agent Query Surface**:
An open-query interface (ADR 0014) where an automated agent composes its own query over MDM, graph, and gold data, guided by a published Agent Query Catalog, instead of reading a pre-materialized Decision Graph Bundle. No Agent-Grade Read gate applies; there is no fixed bundle to gate. Additive to, not a replacement for, the Snowflake Decision Contract and Mongo Decision Projection, which keep gating whatever still reads them.
_Avoid_: Calling this the Agent Decision Surface (distinct concept — that one is the fixed, watermarked, pre-materialized contract), treating an Agent Query Surface result as automatically safe for a Trading Decision, assuming it replaces v1/v2 by default

**Agent Query Catalog**:
The published description an agent uses to compose its own Agent Query Surface query: data definitions (entities, fields, documented meaning, null semantics) and relationships (foreign keys, graph edges) across MDM, graph, and gold. Not a pre-materialized bundle and not query results themselves — only the map an agent reads before writing its own query.
_Avoid_: A running query cache, a fixed answer set, conflating this with a Decision Feature's documented meaning (that's bundle-scoped; this is catalog-scoped and spans stores the bundle never did)
