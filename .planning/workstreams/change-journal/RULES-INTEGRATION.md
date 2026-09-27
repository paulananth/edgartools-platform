# Rules acquisition integration contract for Claude

Rules keeps its existing source files and `rules.rule_version`; no acquisition
configuration table or parallel lifecycle is introduced. Bookkeeping owns
catch-up runs, resource checkpoints and producer completion. Change Journal
owns immutable decision/outcome receipts. Source artifacts own records,
revisions, conflicts and import manifests.

Each source document may declare `acquisition: {version: 1, feeds: {...}}`.
Each exact feed declares `family`, `datasets`, `scope`, `capabilities`,
`completeness`, `required_producers`, and `url_prefixes`. Capability names select
registered operations; they never branch on provider names. `scope` names
required source-owned work-unit keys. The frozen manifest and root run retain
the selected source/feed and dataset identities. Zero work requires an explicit
verified empty scope; absence of a file/listing is insufficient.

Save/prove/approve/activate/resolve remain the existing Rules interface.
Acquisition activation requires the exact body's approval and feed-specific
validation proof with pinned source-owned baseline manifests. No checkpoint
or old decision is imported. MDM registration uses a frozen proven/approved
Rules envelope as authority. Existing `registry_evidence` remains in historical
mapping rows; new Rules attestations use a deterministic version UUID plus the
Rules name/version/digest/proof/approval. A control-policy edit alone does not
create another mapping version.

Journal configuration is `CHANGE_JOURNAL_DATABASE_URL` and
`CHANGE_JOURNAL_MIGRATION_DATABASE_URL`; neither falls back. The fresh database
is `change_journal_clean`. Journal delivery follows the owner's committed
intent in a separate transaction and must verify durable read-back.

Legacy acquisition and native-publication verifiers remain legacy until every
affected feed qualifies; pending historical deliveries must drain on their
original stack. No historical intent may be relabelled as a fresh event.
