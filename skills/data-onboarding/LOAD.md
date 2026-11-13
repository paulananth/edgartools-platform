# check and load: the files are the rules

Part of the `data-onboarding` skill: [SKILL.md](SKILL.md) says when to read this.

The files under `rules/` are the rules. A person or an agent assembles them by hand; nothing is saved,
proved, approved or activated before a run. A run freezes the files it is given under the digest of their
content, and the Rules Database records that digest, so the rules a past run used can always be read.

## Check the changed Rules documents

For one source, run its scoped offline check:

```bash
edgar-warehouse rules check --source <name>
```

This loads that source as a run would. The unfiltered `rules check` scans the
whole Rules tree; use it for a full-tree validation, not a narrow edit. The
local commit guard validates changed `source.yaml`/`quality.yaml`, merge and
pipeline documents, and checks Dataset Contract identity. It does not parse
unrelated Source Extract files; run their owner-specific tests when they
change. CI retains full-tree validation. A refusal in an unchanged legacy
document is not a reason to weaken or rewrite it during an unrelated change.

For a mapping or a quality rule you want to see at work first, run the configured rules over a few invented
files with `tests/support/source_chain.py` (`read`, `combine`, `prepare`, then `records`). The test keeps
only what is its own: the files, each artifact's context and lookups, and the preparation keys.

## load: one command, safe to rerun

```bash
uv run --extra mdm python infra/scripts/local-test-stores.py up <store name>   # a disposable store, first time
edgar-warehouse load --source <name> --target <target> --capture <capture folder> \
  --capture-run <run> --as-of <time> \
  --stores ~/.local/share/edgartools/local-tests/environments/<store name>
```

`load` does the whole path for one source's target ([data-operations](../data-operations/SKILL.md#load-a-capture)):

1. It registers the merge rules and the source's Dataset Contracts in MDM from the files
   (`rules register`; registering what is registered changes nothing).
2. It cuts the capture into bundles and leaves out every document the Change Journal holds as processed
   under these rules.
3. It submits each bundle (`rules run`) and drives it to `complete`.

Load a new source into a disposable store first, read the counts, then load it into the shared store. A
second `load` of the same capture must find nothing to do: that is the whole repeat check, and it costs
seconds.

- **Load every source that can bind the same entities.** A rule that creates entities shows a duplicate only
  when the other sources whose records can match the same entities (by an identifier or by name) are loaded
  too.
- **Count the links MDM accepts, not the links a contract writes.** Only the Merge Stage shows that a link
  resolves. A link with no stated start, from a publication that states no effective time, goes to review.
- **Configuration first.** Before proposing an engine change, find what the rules files already allow (a
  rule's `on_no_match`, a reading's `context`, a reduction's keys or `last`).
- **A merge-rule change moves pinned digests.** Other tests pin a kind's policy digest, so run the whole MDM
  test folder (see Examples in SKILL.md), not only the tests that load the rules.
- **If a run hangs or is killed,** its container stays up. Remove it with `local-test-stores.py stop <name>`.
  Remove only the store your run created; the shared store's container stays.

## A new matching rule

A matching rule declared in a kind's file fires and sends its result to a Steward. It acts alone once
`rules/merge/policy.yaml` lists it under `automatic_rules`:

```yaml
- kind: <kind>
  family: <the rule's family>
  rule_id: <rule_id>
  rule_version: <the rule's version>
  verdict: <a verdict it emits>
```

Listed is on. An edited rule gets a new version, and the entry names it. An identifier matching rule also
needs its namespace's Identifier Contract in the kind's file (authority, sources, normalizer, claim,
compatibility). `rules check` refuses an entry that does not hold, with the reason.

A new domain's order: the classification rule, then the identifier matching rule, then the source.

## Live acquisition

A run that names a feed (`rules run --feed <feed>`) makes requests to a provider. No request to a data
provider is made without the operator's permission for that request; a load over files already captured
needs none.
