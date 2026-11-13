# Mastering console

Design only; nothing here is built, scheduled or part of go-live. Operator, 2026-11-13: "simplify the design use kiss".

## What it is for

One web page where an operator sees how Company, Person and Security records are mastered, changes a matching rule, tries the change on a few invented records and reads why a golden record holds a value. Nothing else.

## Rules of the design

1. **The files are the policy.** Rules live in `rules/merge/kinds/{company,person,security}.yaml` and `rules/merge/policy.yaml`. A change is a pull request, and its review is the review. The console keeps no copy of a rule: no drafts, no revisions, no console tables.
2. **The console calls the code that exists.** Reading and writing a rules file is `files.loads/dumps`; checking it is `files.check`; the digest is `frozen.of`; the merge is `merge_file`; a steward action is `steward.split/resolve`. The console adds no matching of its own and no second rule language.
3. **One page, three kinds.** The same screens serve all three entities, driven by the rules files. No page is written for one kind and copied for another.
4. **Every claim is something the engine says.** A badge shows a check or a run result, never a guess. A result that is missing says "not recorded".

## Three questions, kept apart

1. **Matching** finds the golden record a new record belongs to.
2. **Consolidation permission** decides whether two existing golden records may become one. Joining a record to one golden record never grants it.
3. **Survivorship** picks the value each field shows, after the first two. A source priority never proves identity.

Each screen shows which question a rule answers.

## Where each part lives today

| Part | Code | The console does |
| --- | --- | --- |
| Authoring | `rules/` files, `edgar_warehouse/rules/files.py` | Reads and writes through it |
| Rules in force | `automatic_rules` in `rules/merge/policy.yaml`; a rule listed there with its kind, family, id, version and verdict is allowed | Shows whether each rule is listed. A change in the console never alters a running policy |
| Check and digest | `files.check_document`, `frozen.of` | Calls them; the browser never decides a file is valid |
| Registration | `frozen.register` through `rules register` | Nothing; registering stays a command |
| Rules a run used | `rules_used` (`Rules.history/body`) | Shows them for a run |
| Merge | `mastering/merge.py` `merge_file` | Never writes a golden record |
| Stewardship | `mastering/steward.py` `split/resolve` | Preview and confirm only |
| Catalog | `rules/catalog.py`; OpenMetadata is published to, not authored in | Nothing |

There is no save, prove, approve or activate step for a rule. Older notes and skills that still mention one are wrong; fix them in a separate change, and do not bring the step back to match them.

## Screens

| Screen | Shows | Needs |
| --- | --- | --- |
| Policy | For one kind: its identifier routes, name fallback, outcomes (create, join, wait, review) and each rule's version | Read the rules files |
| Field selection | Source order per field, freshness and clear rules, and which source won each value of one golden record | Read rules; read one golden record with its sources |
| Change a rule | A form for the rule's parameters, a before and after view, the rules file as a patch to commit | `files.check` on the changed file |
| Try records | Invented records run through the real engine, baseline against the change: created, joined, waiting or review, and the fields that changed | A disposable local store (`local-test-stores.py up`), never the shared or hosted one |
| Golden record | Source contributions, identifier holders, history and open review reasons | Read the MDM store |

Steward actions (resolve a review, split two identities) come after these: preview first, then one confirmed call to `steward.resolve/split`. The confirm re-reads the review under the store's lock and refuses if it changed since the preview.

## What the merge must keep (the engine's own rules)

- One record has one kind; a Company and a Person never join on a shared value.
- All applicable identifiers are searched; a name or a source priority never overrules an identifier conflict.
- Joining one golden record does not allow consolidating two. Existing exclusions stand.
- Which identity survives and which value wins are two decisions.
- Every source record and every losing value is kept.
- Replaying the same file changes nothing; a failed merge leaves no partial write.

## Policy by kind

| Kind | Look at | Cases that must stay separate |
| --- | --- | --- |
| Company | CIK, LEI, CRD and the other declared identifiers; name and place only as a fallback | Similar names with different authoritative ids; a renamed company stays one |
| Person | Classification and CIK routes; role is not identity | Same name, two people; a changed employer is not a new person |
| Security | CUSIP, ISIN, listing and share-class FIGI; tickers are lookup only | A reused ticker; two share classes; an issuer link is not identity |

## Build

- **Frontend:** plain HTML and a little script, served by the same Python application. No framework and no build step until a screen needs one.
- **Backend:** one small Python application (FastAPI) that calls the functions above. No browser-supplied command, path, SQL or URL reaches the code; documents are named by commit and path from the repository.
- **Calls:** `GET /policy/{kind}`, `GET /masters/{id}`, `POST /check` (a changed file, returns the diagnostics and digest), `POST /try` (a changed file and invented records, returns the baseline and the change side by side). Steward calls: `POST /steward/preview`, `POST /steward/confirm`. Numbers that can exceed 2^53 cross as strings.
- **Access:** the deployment's own login in front of the application; the application runs on loopback until that is set. Local development uses invented data.
- **Order:** read screens first, then Change a rule, then Try records, then steward actions. Each is its own ticket and PR; do one kind end to end before the other two.
- **Tests:** each screen's call is tested against local PostgreSQL with expected answers written in the test; the "Cases that must stay separate" above each get a test.

## Left out on purpose

Drafts and revisions, a console schema and audit tables, roles and a permissions model, idempotency keys, a registration route, a graph editor, a canvas, a plug-in language, machine-learning matching, and a screen per kind. Each can be added when someone needs it and says why.
