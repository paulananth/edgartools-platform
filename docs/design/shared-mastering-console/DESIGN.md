# Shared mastering and policy console

Status: proposed implementation design, 2026-11-13. This handoff includes a functional, invented-data UI prototype and a proposed architecture diagram. It does not install a production UI, change matching policy or authorize a source load.

Baseline: `9b00663adb4dc859be5ac21be31b75248e2fb9cd`. Reconcile current main and overlapping work before implementation. The files and functions cited below were inspected at that revision; existing tests were inspected, not rerun as mastering qualification.

## 1. Outcome and scope

Give an operator one interface to understand and maintain Company, Person and Security policy, see how an assertion passes through mastering, test a proposed change, and inspect why a record or value was selected. Keep one shared Merge Stage. Entity/source variation remains configuration interpreted by existing Rust/Python code; databases retain authoritative enforcement and atomic persistence.

The implementer must deliver a production web interface and backend in this repository. The attached [prototype](prototype.html) is a screen/interaction reference, not the backend or a second matching engine. The [architecture viewer](architecture.html) and its [editable source](architecture.json) describe the proposed system, not a deployed service.

MVP includes policy browsing, schema-driven forms, immutable draft revisions, generated flow visualization, validation/diff/export, isolated scenario tests, registered-versus-file-versus-run comparisons, field provenance and review inspection. A later delivery adds controlled MDM registration and confirmed stewardship using the same domain operations. Provider capture, arbitrary SQL, workflow programming on a canvas, general ML matching, and new entity domains are outside this delivery.

## 2. Existing authority — do not reconstruct the retired lifecycle

| Responsibility | Current implementation | Design consequence |
| --- | --- | --- |
| Authoring | `rules/` files; [files.py](../../../edgar_warehouse/rules/files.py#L1) owns loading/writing/validation | Draft forms must round-trip the existing document semantics. Files remain the release artifact. |
| Effective matching rules | Exact entries in `rules/merge/policy.yaml:automatic_rules`; [activation.py](../../../edgar_warehouse/mdm/activation.py) | Listing the matching kind/family/id/version/verdict permits that rule. Show inclusion explicitly. A draft toggle must never change running policy. |
| Validation/freeze | [files.check_document/check](../../../edgar_warehouse/rules/files.py#L404), [frozen.of/export](../../../edgar_warehouse/rules/frozen.py#L13) | Reuse these functions; the browser cannot declare a policy valid or calculate an authoritative digest. |
| MDM registration | [frozen.register](../../../edgar_warehouse/rules/frozen.py#L33) through `rules register`, owner connection | Registers policy and Dataset Contracts. Registration is not an approval or a run. |
| Rules history | [Rules.record/history/body](../../../edgar_warehouse/rules/db.py#L60), `rules_used` | Immutable documents actually frozen for runs; not a draft, approval or activation database. |
| Run submission | [rules CLI _run](../../../edgar_warehouse/rules/cli.py#L58), frozen document/artifact and Bookkeeping submission | A run pins its inputs and rules. Editing files does not change an in-flight run. |
| Merge | [mastering worker](../../../edgar_warehouse/workers/mastering_merge.py#L77), [merge_file](../../../edgar_warehouse/mastering/merge.py#L110) | One function, grouped by kind; UI does not write golden records. |
| Stewardship | [steward.split/resolve](../../../edgar_warehouse/mastering/steward.py#L33) | Existing preview/confirm behavior is reused; a new HTTP precondition wrapper is required. |
| Catalog | [rules/catalog.py](../../../edgar_warehouse/rules/catalog.py) | OpenMetadata is a published catalog, not the authoring service. |

There are no current `Rules.save/prove/approve/activate` methods or corresponding CLI lifecycle commands. Some older notes/skills still mention them. Implement against the current code, and reconcile those instructions in a separately reviewed documentation change; do not reintroduce that lifecycle to satisfy stale text.

## 3. Design decisions

1. **One algorithm, three policies.** No CompanyMerge/PersonMerge/SecurityMerge class hierarchy.
2. **Three independent questions.** Matching finds the golden identity; explicit consolidation permission governs two existing identities; survivorship selects values afterward. A source priority never proves identity.
3. **A row is evidence.** An assertion carries one settled kind, identifiers, values and provenance; it is not a complete golden record. Candidate lookup and stored history remain necessary.
4. **The graph is generated.** The engine owns stage order and rule-family semantics. Users edit supported rule parameters in forms, not arbitrary edges or executable scripts.
5. **Drafts do not affect runs.** The UI exports reviewed rule files for Git. MDM registration and operational use are explicit actions against exact digests.
6. **Code only for a demonstrated gap.** Existing defaults, per-field overrides, field-group authority, freshness, conflict handling and waiting/release must be reused. LEI-specific name-pair generalization is conditional on a concrete second workflow.

The application service is a thin facade over domain operations. Its cost is maintaining request/authentication/serialization contracts; it must not acquire its own matching semantics. A per-entity Strategy hierarchy and a general plugin language add indirection without an evidenced need. Current [merge history](https://github.com/paulananth/edgartools-platform/commits/9b00663adb4dc859be5ac21be31b75248e2fb9cd/edgar_warehouse/mastering/merge.py) shows shared-path changes, not three duplicate algorithms.

## 4. Business flow and invariants

Source reading → prepared assertion with settled kind → same-kind candidate retrieval and identifier matching → configured name fallback → create/join/wait/review → affected master projection and field selection → atomic commit → dependent relationship resolution and publication through their existing owners.

This is a business view. The actual implementation order is owned by [merge._merge](../../../edgar_warehouse/mastering/merge.py#L211), with classification earlier in [adapters.classify_record](../../../edgar_warehouse/mdm/adapters.py#L182). Relationship projection and publication have separate owners and must not be represented as new inline writes invented by the UI.

Required invariants:

- One assertion has one entity kind. A Company and a Person sharing a value cannot join across kinds.
- Search all applicable identifiers under their contracts. A display name or source priority cannot overrule a configured identifier conflict.
- Joining one golden record does not silently grant permission to consolidate several. Preserve existing exclusions and review outcomes.
- Identity survivor selection is separate from value survivorship. Preserve the current older-survivor behavior unless separately changed and proved.
- Keep original assertions and nonwinning values. Distinguish unknown, clear, retract, empty and absent semantics using existing contracts.
- A relationship never creates the other endpoint or changes an assertion's kind. A Security may wait for its issuer link while retaining its own identity.
- Unchanged replay changes no mastered content. Recoverable failure leaves no partial identity, identifier, decision or progress effects.
- Fixed safety checks, destination constraints and authorization are not removable graph nodes or editable policy options.

## 5. Entity policy requirements

Build a route inventory from every current source Dataset Contract and kind policy; do not hard-code source lists in the UI. Each route records source, declared/classified kind, rule id/version/family, identifier namespace, issuer/lookup role, cardinality, predicates, no-match and several-match outcomes, consolidation permission, automatic_rules inclusion, field/profile authority and relationship requirements. Inventory rows must map to a rule location and an acceptance case.

| Entity | Required policy review | Explicit negative cases |
| --- | --- | --- |
| Company | CIK/LEI/CRD and other declared routes; identifier-first matching; source-qualified name/place evidence; field authority and freshness; role profiles share Company identity | Similar names with contradictory authoritative IDs; ambiguous pair; rename remains the same identity; separate legal entities stay separate |
| Person | Classification and CIK routes across submissions/ownership; role versus identity; source priority; name-only cases remain unresolved unless sufficient approved evidence exists | Same name for two people; Company/Person sharing an identifier; changed employer does not create a new person |
| Security | CUSIP/ISIN/listing FIGI/share-class FIGI distinctions; lookup-only symbols; source-specific fallback keys; conflict/consolidation contracts; issuer and listing associations | Reused ticker; share-class key conflicting with another identifier; distinct classes; issuer relationship mistaken for identity |

Baseline files: [company.yaml](../../../rules/merge/kinds/company.yaml), [person.yaml](../../../rules/merge/kinds/person.yaml), [security.yaml](../../../rules/merge/kinds/security.yaml). This design does not change their business decisions. Proposed new behavior needs its own configured version, explicit expected answers and the established approval procedure.

### Policy representation and round-trip

Use existing document shapes; do not create a parallel UI policy language. The backend capability response describes supported families/primitives, parameter types, editable paths, enum values, engine stage, compatibility, and documentation/source pointers. It derives vocabulary from existing catalogs/validators. The small stage descriptor is versioned with the engine, covered by an execution-order test, and is shared by validation/graph rendering rather than copied into the browser.

Forms initially expose existing classification/matching predicates, identifier contracts, outcomes, automatic_rules inclusion, default/per-field/group source priority, and freshness/clear rules. Unknown or not-yet-supported properties remain visible read-only and are preserved when other fields change. Refuse edits that cannot round-trip. Use `files.loads/dumps/write_policy/write_source` and existing validation; do not use a permissive browser YAML parser. Comments may be normalized by the existing writer; show this in the export diff rather than claiming byte preservation.

IDs, counters and BIGINT values cross JSON as strings. Exact decimals use decimal strings with explicit schema type. Do not round through JavaScript Number or silently change existing rule digests/number semantics; any existing parser precision gap discovered by a required rule value is a separately tested engine fix. Request scalar envelopes distinguish text, integer, decimal, boolean and null, and the backend converts only according to capability metadata.

## 6. Proposed application architecture

New components below are proposals, not existing runtime services.

- **Frontend:** React with TypeScript, same-origin API, semantic forms and SVG flow view with an equivalent keyboard list. No graph-editor dependency is needed for the bounded logical graph initially. Choose lockfile versions during implementation and qualify them in CI. Official references: [React](https://react.dev/), [TypeScript](https://www.typescriptlang.org/docs/).
- **Backend:** Python/FastAPI adapter with public application functions for documents, drafts, graph, validation, scenario tests, registration and stewardship. Reuse domain functions directly; do not execute browser-supplied shell commands. [FastAPI documentation](https://fastapi.tiangolo.com/).
- **Draft/audit persistence:** a new SQLAlchemy-owned `console` schema in the configured Rules database (portable table names where schemas are unavailable), with a new owner migration and restricted grants. Existing `rules_used` remains immutable run history and is not repurposed. No infrastructure is provisioned by this design task.
- **Test execution:** a bounded server-owned job using existing Bookkeeping/worker patterns where a suitable operation exists; add a narrowly named operation if absent. No simulation interpreter in JavaScript. A test gets a pinned runtime, policy, captures, as-of and isolated test destination; it never targets shared/live MDM.
- **Release/registration:** exported rule bundle goes through repository review/CI. An authorized registration operation reads the merged artifact by exact commit/digest and calls `frozen.register`. Browser credentials never reach the owner connection.
- **MDM reads/actions:** inspection uses existing store readers and indexed lookups. Later confirmed actions invoke existing stewardship through a fresh-state guard; no alternate table writer.

Suggested ownership paths for implementation (new unless already present at implementation time): `web/mastering-console/` for UI; `edgar_warehouse/console/` for HTTP/application/draft storage; `edgar_warehouse/rules/` for public document projections; `edgar_warehouse/mastering/` for necessary guarded stewardship changes; existing storage tests for domain effects. Keep authentication and transport out of merge computation.

## 7. UI specification

Global context always shows environment, entity kind, source/target selection, document reference and origin: **draft**, **files at commit**, **registered policy**, or **rules used by run**. A digest prefix is a display label only; requests carry the full digest. Environment never silently changes when selecting a run.

| Screen | Behavior | Empty/failure behavior |
| --- | --- | --- |
| Flow | Switch entity/source; show physical target steps separately from logical merge stages; click node to inspect rules, parameters, predicates and location; highlight automatic versus declared rules | Unsupported capability: visible read-only node with reason. Missing run trace: “Not recorded”, never a fabricated path |
| Rules | Search/filter inventory; edit supported parameters and automatic_rules inclusion in a draft; show before/after and version changes | Invalid field errors point to the document/path. Concurrent edit offers reload or a new draft, not overwrite |
| Field selection | Maintain default/per-field/group source order, eligible clear operations and freshness; inspect inherited versus explicit values and nonwinning contributors | No applicable rule/value is shown explicitly; no silent “latest wins” default |
| Try a record | Choose pinned invented fixture/cohort or authorized retained capture; compare baseline and draft using the real engine; show candidate reasons, outcomes, changed fields and unresolved counts | Queue/running/cancelled/timed-out/failed are distinct from a completed test; no pass badge from transport success |
| Review/export | Validate, view semantic and serialized diff, inspect coverage, download exact bundle/patch, navigate to Git review; compare merged versus registered digest | Editing invalidates prior validation/test associations for that draft revision; unmerged export cannot be registered |
| Golden record / review | Read source contributions, identifier holders, selected field provenance, history, relationships and open review reasons; later preview resolve/split | Unsupported review reason is read-only. No arbitrary “merge selected” action is exposed |

Use plain business labels (“Matching rules”, “Field selection”, “Golden records”). A runtime badge reports evidence, not decoration. A rule in automatic_rules is “Enabled in this policy”, not “source live”; separately show actual run usage. A draft choice is never labeled approved or deployed.

Accessibility: every form input has a label, graph controls support keyboard activation and focus, status changes have live regions, colors have text equivalents, source-order controls have up/down buttons, dialogs restore focus, and all functions work at 390px width without page overflow. Respect reduced motion. Tables may scroll within their own labeled region. Do not put secrets, connection strings or raw production values in prototype/PR screenshots.

### Prototype contract

The included HTML uses one shared data-driven screen for all three entities. It supports changing entity, inspecting flow stages, editing a draft route and source order, local validation, an explicitly illustrative scenario, local save, JSON export and reset. All sample sources/records are invented. Its scenario labels are hand-authored design examples, not real engine results. Server proof, Git publication, registration, live data and stewardship commits are absent/disabled and explained. Local storage/export contains a design draft, not runnable rule files. Production implementation must replace it with the API below.

No maintained application theme was found at the baseline. The prototype therefore uses the Lavish default DaisyUI luxury theme (and corporate light theme), with Tailwind/DaisyUI CDN styling and local layout CSS. It retains a basic fallback layout; full visual styling requires those CDN assets. The production app must bundle its assets and use a locked dependency set.

## 8. API and concurrency contract — all routes proposed

Prefix `/api/mastering/v1`. Responses have `request_id`, `schema_version`, `environment_id` and the relevant full content/runtime references. No response returns private connection configuration. Pagination uses opaque cursors and indexed bounded queries.

| Method/path | Request → result | Owner/reuse |
| --- | --- | --- |
| GET `/capabilities` | runtime reference → allowed kinds/families/primitives/edit paths and stage descriptor | existing catalogs/validators + new projection |
| GET `/documents` | origin, kind/source, commit/run/digest → document list + provenance | files/frozen and Rules.history/body; registered read through adapter |
| GET `/documents/{ref}` | opaque server reference → body projection, typed scalars, full digest | server allow-listed document identity; no arbitrary path/URL |
| GET `/flows` | document ref, target, kind/source → nodes/edges/list and rule pointers | frozen target steps plus engine-owned logical descriptor |
| POST `/drafts` | base document refs + title → draft id/revision/ETag | new console store |
| PATCH `/drafts/{id}` | typed semantic edits with If-Match → new revision/ETag | existing serializer/validator; reject protected/unknown edit paths |
| POST `/drafts/{id}/validate` | exact revision → diagnostics + canonical export digest | files.check + frozen.of over complete staged bundle |
| POST `/drafts/{id}/tests` | revision + approved fixture/capture ref + as-of → 202 job ref | isolated actual engine runner; baseline and candidate references pinned |
| GET `/tests/{id}` | → job state, checks, coverage and artifact refs | server-owned test record, Bookkeeping references |
| POST `/drafts/{id}/exports` | validated revision → exact file bundle/patch, manifest, base commit and digest | existing writers + mapdoc; no provider access |
| GET `/runs/{id}/policy` | → frozen document + registered comparison + stage evidence | Bookkeeping/artifacts + Rules.body |
| GET `/masters/{id}` and `/reviews` | → authorized bounded inspection and lineage | current MDM readers; index support must be verified |
| POST `/registrations/previews` | merged commit/artifact + expected registry state → effect summary/token | trusted fetch, validate, frozen.register planning adapter |
| POST `/registrations` | token + reason + expected state → durable receipt or conflict | authorized owner operation; later phase |
| POST `/steward/previews` | existing action (`resolve` or `split`), target, choice/reason → preview/token | steward.resolve/split with confirm false |
| POST `/steward/commits` | preview ref + expected generations + reason → receipt or conflict | guarded domain call; later phase |

The prototype does not implement these endpoints. Expose public service functions where CLI helpers are currently private, then make CLI and HTTP reuse them; do not duplicate their logic or turn every helper into a generic framework.

Writes require authenticated identity, server-side role/environment permission and an Idempotency-Key. Draft edits additionally require If-Match. Missing precondition → 428; stale revision → 412; incompatible live state → 409; invalid field/document → 422; denied → 403; unavailable store → 503 with safe diagnostic. Same idempotency key plus same principal/environment/body returns the original result; different body returns 409. Persist command intent and deduplication with its authoritative operation, not only in an HTTP cache. A disconnect after commit is recovered by receipt lookup; never invite an unguarded retry.

Draft save returns the saved revision, not success inferred from a click. Failed save preserves unsaved local form values and marks them unsaved. Validation/test/export results are keyed by full draft content digest, runtime, inputs and as-of; any changed key makes them historical evidence for that revision rather than current proof.

### Graph projection contract

Each node has stable id, layer (pipeline/logical), stage, label, current/proposed capability state, rule refs (document + semantic pointer + rule id/version), editability, and diagnostic refs. Edges carry outcome/condition labels. Display coordinates are optional user preferences, stored separately from policy. Graph generation is deterministic for the same document/runtime references. Unknown rule families are visible and block mutation/export if backend validation rejects them.

A trace overlay is a separate response with run/attempt/input references and observed events. Only recorded events can be highlighted as executed. Static policy applicability is labeled “Configured”; missing fine-grained trace is “Not recorded”. A logical graph is not a claim that every pictured rule ran. Provide both source-first target steps and entity-first merge policy views without duplicating rule definitions.

## 9. Data ownership, authorization and safety

Proposed console tables: `draft` (owner, base refs, current revision), append-only `draft_revision` (body/ref, digest, actor, reason), `test_run` (pinned references, state, result refs, deadline), and `audit_event` (action, actor, environment, object refs, outcome). Use BIGINT for revisions/counters and exact numeric representations. Do not add another master or identifier table. Use existing Bookkeeping command persistence where available; add only the missing console records with owner migrations and restricted grants. Policy digests remain computed by existing canonicalization.

Roles are application capabilities: reader, author, tester, registrar, steward. They map to the organization's authenticated groups in deployment configuration. Reader can inspect only permitted environments/data. Author can edit/export drafts; tester can run against allocated test stores; registrar can register approved merged artifacts; steward can confirm only supported review actions. Git review supplies code/configuration review; it is not recreated as a fictitious Rules DB approval row. Any required separation of duties is enforced by deployment role mappings and the established operator procedure.

The service requires configured OIDC authentication and a server-validated session; same-origin secure HttpOnly cookies, CSRF protection on writes, TLS at deployment ingress, deny-by-default origins and role checks on every endpoint. Local development uses invented fixtures and an explicit test identity adapter; that adapter must refuse non-loopback/non-test startup. Live write routes remain unavailable until real identity/role configuration is qualified. No identity-provider vendor is selected here.

UI registration changes only registry content. It neither acquires files nor starts a source load. Changing automatic_rules is a business policy change visible in the Git diff and governed by the existing onboarding/refining procedure. Existing in-flight runs retain their frozen policy. Re-registering an old policy does not erase newer effects; rollback means selecting a reviewed prior artifact for future runs and assessing compensating/reprocessing work explicitly.

Before enabling HTTP stewardship, close a current freshness gap: existing preview/confirm functions are not a persisted preview-token protocol, and some lookup reads occur before taking the write lock. Add a narrow domain wrapper that re-reads affected review, members, exclusions and policy under the destination lock, compares the preview's expected state, and executes once in the same transaction. Token is opaque, short-lived and bound to actor, environment, action, target set, policy/runtime and observed state. A changed state requires another preview; token possession is not authorization. Tests must inject a competing change between preview and commit and assert refusal with zero partial writes.

Server resolves opaque capture/artifact references from a registered allow-list; no user-controlled filesystem roots, SQL, shell, provider URLs or arbitrary fetches. Keep private datasets outside repository artifacts and redact diagnostics by sensitive key names. Store detailed diagnostic results privately; public reports contain counts and invented examples only.

## 10. Simulation, evidence and failures

A production “Try a record” is a bounded actual-engine run, not a browser score. Baseline and draft receive the same invented/cohort inputs, registered test contracts, runtime, as-of and initial state. Existing-master cases require a pinned seed state or a verified isolated setup. Preserve original captures. A test record reports created/joined/waiting/review/consolidated outcomes, candidate reasons where available, field winners/losers, relationships, content hashes and check assertions. Missing trace detail is not fabricated.

Every test has a deadline, cancellation outcome and cleanup owner. Stop disposable containers after every exit; retain private failed-run artifacts for diagnosis/resume. A narrow test is not whole-source readiness. Never use a shared/live store for experimental merge replay or create a full store for a pure document check.

Registration is a transaction over its existing registry owner where possible. If a release operation spans systems, record stage receipts and expose partial status; retries resume idempotently, not by announcing full success. API GET may use bounded UI refresh/backoff; agents inspecting already-running proofs retain the repository's 30-minute check rule. No endless server jobs or CI watchers.

## 11. Implementation sequence and acceptance gates

| Slice | Implementer deliverable | Acceptance gate |
| --- | --- | --- |
| 0 — baseline and contract inventory | Inventory all three kinds/current sources; reconcile retired command references; map each required behavior to existing configuration, missing configuration or missing engine capability | Exact baseline/runtime recorded; no invented CLI/service contract; overlapping ownership resolved |
| 1 — read-only console | Authenticated document/registered/run readers, capability projection, physical/logical graph, entity/source filters, field and review inspection | Every graph node links to policy/runtime evidence; configured vs executed distinguished; no mutation credentials; keyboard/narrow viewport checks |
| 2 — draft authoring and export | Forms, typed semantic patching, revision concurrency, validation, diff, mapdoc and export bundle | Round-trip each current entity/source contract without dropping unknown properties; concurrent edits refuse; export digest matches existing freeze |
| 3 — actual-engine tests | Isolated baseline/candidate job, seed fixtures, result/lineage comparison, deadlines/cancellation | Explicit expected results per source/kind; no writes to shared MDM; replay stable; failed jobs cannot yield pass |
| 4 — guarded operations | Authorized merged-artifact registration; preview/freshness-guarded resolve/split, idempotent receipts | Stale registry/preview and duplicate requests tested; role boundaries enforced; disconnect-after-commit returns original receipt |
| 5 — evidenced shared capability gaps | Only the capabilities inventory proves necessary; conditional namespace/evidence profile extension rather than per-entity code | Existing behavior preserved by explicit compatibility fixtures; affected installed adapter/caller matrix passes |
| 6 — release qualification | Standards/Spec/GoF review, user acceptance, approved hosted-target deployment plan and bounded source proving | Qualified target and source scope explicit; source activation/load remains its own authorized operational action |

Each slice is a separate ticket/PR on a fresh branch. Cut through one entity end to end first while making the UI metadata-driven from day one; extend configuration/cases to the other two before claiming all-three completion. Do not use Company-specific route code as the template for copied Person/Security screens.

### Required behavior matrix

All three: create; join an existing identity; conflict/review; configured wait and release; no cross-kind join; field precedence; unknown/clear/retract; correction/history; unchanged replay; rollback; alias/readback. Cover each current source-specific route, not only one fixture per kind. Add shared conflicting-third-record cases (A matches B, B matches C, A conflicts with C), consolidation permission and split exclusion.

Company: identifier disagreement, unique/ambiguous name-place pairing, either arrival order, rename. Person: same-name negatives, submission/ownership convergence and classification uncertainty. Security: listing FIGI consolidation, share-class conflict, reused ticker lookup, distinct classes, issuer waiting/resolution. Reversal tests include later updates and relationship/listing reassignment, not only immediate undo.

UI/API: lost save response; stale ETag; unsupported rule property preserved; >2^53 integer and exact decimal round-trip; denied environment; test timeout/cancel; registry stale state; post-commit disconnect; changed preview; graph/table keyboard parity; dark/light/mobile; safe plain-text rendering of rule/source values. Run only affected local tests within five minutes; CI runs the complete required suite. Selected-engine claims require the actual installed caller matrix, not browser or mocked persistence proof.

## 12. Vendor rationale and handoff limitations

The preceding [research PR #1732](https://github.com/paulananth/edgartools-platform/pull/1732) compares Fencore, Rimes/Matrix and Informatica; [PR #1731](https://github.com/paulananth/edgartools-platform/pull/1731) traces the shared merge. Their draft/merge state is independent of this design. Useful primary sources: [Fencore model/mastering/governance](https://www.fencore.co/products/datahub/full), [Rimes data management](https://www.rimes.com/solutions/data-management/), [Matrix positioning](https://www.rimes.com/rimes-fact-sheets-investops-europe-paris/), [Informatica matching and field survivorship](https://www.informatica.com/blogs/powering-digital-business-with-intelligent-multidomain-master-data-management-saas.html).

These sources motivate visible configuration, separate identity/value decisions, lineage and stewardship. They do not prove a shared internal vendor implementation or establish our conflict thresholds, reversibility or hosted deployment readiness. No vendor algorithm, numerical confidence threshold or machine-learning model is required by this design.

The deployment environment, OIDC group bindings and network exposure are supplied through a reviewed deployment configuration before live access. Hosted MDM targets remain Snowflake Postgres and Databricks Lakebase Postgres, with local PostgreSQL 16 for proving. This document does not select a new hosted service or provision infrastructure.
