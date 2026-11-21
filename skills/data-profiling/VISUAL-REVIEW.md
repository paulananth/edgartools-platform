# Visual review of profiling evidence

Use after `profile_data.py run` and before `approve`. The page is a private, read-only aid for reviewing findings; it neither approves nor changes data.

## Build a candidate summary

Read existing `REPORT.md` and `findings.yaml`; do not rerun profiling to make the view. Start with parts classed `master`. Also include `silver` parts whose `master` test group ties for the top score above 0.5; label these unresolved candidates and preserve `class: silver`. For each candidate, show parent/source/grain and `derived_from` context when present. A high `master` score or unique key on an event/transaction-derived part is structural evidence, not proof of a shared business domain.

- part label, selected class, confidence, runner-up and each test's class/name/value/pass flag as present; for `silver`, group tests by class and show top scores/ties without relabeling or reconstructing missing tests;
- any `proposed_kind` draft and generated question/recommendation, labelled provisional. The generated recommendation is not evidence that the new-kind tests passed and is never approval.
- found or designed record key, with null/unique counts and persistence state;
- identifier shapes, check-digit rates, and identifier-pair counts;
- incoming/outgoing links, coverage, cardinality, scan mode, and link evidence;
- embedded-entity evidence only when `derived_from` and `derived_evidence` exist; include identifier count, follow rates, and disagreement counts. A follow percentage alone does not establish a distinct entity.
- temporal roles, versions-per-key evidence, and explicit unknowns.

Use counts and field labels, not record values. Never copy raw rows, sample or top values, personal values, key hashes, database addresses, credentials, or secret paths into the candidate. Do not pass the whole `REPORT.md` or `findings.yaml` to Archify; read them locally and write a sanitized summary. When a required signal is absent, show it as unknown. Links and identifier pairs are structural evidence, not proof of business meaning or join authority.

## Keep EDA focused and adaptive

Use EDA only on fields that feed a candidate class, key, identifier, link, relationship, or matching decision. Read existing shape counts first; widen a field only when its sample shows multiple shapes, an unparsed shape, or rows that fit none. For entity discovery, widen only a candidate signal that could change the class or handoff. Stop when the next targeted pass adds no new identity, relationship, or time evidence. Do not preview rows, plot every column, remove duplicates, impute values, generate identifiers, or mutate the input during profiling.

A `master` class is structural evidence, not a business-domain verdict. Show measured persistent-identifier, lifecycle, independent-reference and source-coverage evidence when present; missing evidence stays unknown. When NER runs as a companion to this profile, report mention type/count and model version as extraction evidence only; do not expose spans or treat mentions as identity links. If text or a recognizer is unavailable, mark NER not assessed. Entity resolution remains Data Modeling/MDM. A transaction-grain child may identify an event, not a shared master domain. `proposed_kind` and generated recommendations remain drafts, never proof or approval; one delivery cannot establish persistence. Data Modeling decides the model; the operator decides when a ruling is required.

## Create and use the Archify view

Use the Archify skill's explainer workflow to create one local page in the private profiling output folder. Show the candidate and its evidence, the uncertainty, and the next owner. Keep the HTML, candidate Markdown, receipts, and any summary outside the repository; never commit or publish them. Use repository source citations for code claims, not source-data examples.

If Archify cannot finalize the page, report the blocker and stop before requesting approval. Otherwise, show the local HTML link together with the text report. Ask any remaining question one at a time. The page is not an approval control: wait for the operator's explicit words in chat, then run `profile_data.py approve --words` with those exact words. Without that approval, do not run `compare` or claim the findings are approved.