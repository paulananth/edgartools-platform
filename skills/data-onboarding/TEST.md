# test: run it on real captured files and record the result

Part of the `data-onboarding` skill: [SKILL.md](SKILL.md) says when to read this.

### test: run it on real captured files and record the result

**Recording a run: two Postgres servers.** `rules test --stores <folder>` runs the
chain in disposable stores (start them: `uv run --extra mdm python
infra/scripts/local-test-stores.py up <name>`, then `stop <name>` and remove the
container after), and `--version` records the result in the operator's Rules
Database. Configure that connection through [Connection URLs and environment](../data-platform/SKILL.md#connection-urls-and-environment);
never use that shared store as `--stores` (the command refuses: the stores'
Rules Database is the test's sandbox). Then
`rules pending` and `rules approve` under the standing words. A small invented
capture is enough for a source whose rules are already proved on real files
(two files, every step verified, second pass changed nothing: about 30 s).

1. **Captured-file qualification.** Use 5–10 receipt-verified records first,
   with source hashes and publication facts taken from the capture. Execute
   the candidate `read:` contract with the configured engine and select
   precisely the records that `mdm.prepare` will send (whole rows, or its
   explicit `record_column`). Follow data-platform Parse and Master for the
   worker flow. Local tests may use a disposable candidate pipeline and
   approval fixture; label these as test-only, not an active Rules version.
   - Compare reading against retained readers when replacing them: values,
     types, order, refusals, counts and complete evidence. Preserve full
     publication checks and bounded streaming for numbered archive releases.
   - For a diagnostic normalization pass, use
     `edgar_warehouse.mdm.adapters.normalize` with `contract=`,
     `source_code=`, `policy=files.policy(root=<draft folder>)` and captured
     publication facts. This tests mapping and quality only; it does not
     prove installed parsing, leases, receipts or MDM commits.
   - **A test over invented files** runs the configured rules through
     `tests/support/source_chain.py` (`read`, `combine`, `prepare`, each
     checked by its worker's verifier, then `records`). The test keeps only
     what is its own: the files, each artifact's context and lookups, and the
     preparation keys. Never copy the chain into a test.
   - **Prove each relationship the source states.** On invented records through the real merge, a record that mentions a
     party with no golden record makes only its own golden record and no link; when the mentioned party's own record is
     mastered, the link resolves and both keep their own entity types. A relationship never creates a golden record.
   - Check the kind's merge rules accept the source. A source missing from
     `defaults.sources` fails its whole batch. Check `defaults.sources` (a
     kind with its own check in code, run it; see Examples). Adding a source to an
     existing kind is a merge-rule change: log it for the operator.
   - **A merge-rule change moves pinned digests.** Other tests pin a kind's
     policy digest, so run the whole MDM test folder (see Examples), not
     only the tests that load the rules. A kind whose digests are pinned
     layer by layer gets the change as one new layer: peeled, the policy
     is the one before. A new kind's own rules leave another kind's pins
     alone (a kind's pins cover its own part of the policy); a change to the shared
     part (relationship types, reference pins) moves them, and moves the
     integration answer file's whole-policy digest too.
   - **A new kind:** records are blocked with `classification_not_activated`
     until its classification rule is switched on. That is expected: the
     order below switches it on first. To see what it would do, add the
     verdict to a copy of the policy in memory only, and label that pass as
     a test input.
   - Run affected configured-engine and retained equivalence tests:
     `uv run --no-sync pytest -q <those files>`. Prove the full installed
     parse → prepare → merge path only when the change needs it
     ([mdm-engineering](../mdm-engineering/SKILL.md), "Choose the cheapest
     proof"). Record assertions, identities, quality counts and deferrals,
     not only row totals.
   - `normalize` runs the quality checks. Each record shows what they did
     under `provenance.quality`, and an `exception` raises
     `UnsupportedRecord("quality_<id>")`. Report the counts
     (`edgar_warehouse.mdm.quality.counts(records, deferred)`) and up
     to 10 examples of each.
   - Report the run report checks too: per source, records and those set
     aside, the empty-value rate per field and the newest record's age
     (`quality.run_checks([quality.profile(records, deferred)], as_of=...)`;
     a Merge Stage run keeps them as `checks` in its report, `mdm.run.report`).
     They never block.
2. **A proving run, for anything that matches records, and only once.** A
   source whose last proof can be carried forward runs none. Which proof a change needs, and when the full installed proof is
   required, is in [mdm-engineering](../mdm-engineering/SKILL.md), "Choose
   the cheapest proof". For a new domain,
   nothing is switched on yet. So the run registers a **copy** of the
   policy, with the new rules added to `automatic_rules` and each stamped
   `approved_by: proving-run` and `reason: "Proving Run only; not an
   approval"`, in the disposable database only. The body the operator later
   approves differs only in those fields (an earlier proving run does
   exactly this; see Examples).

   **A source that declares a target** (`mastering`, unless `--target`
   names another, such as one target per kind of identifier asked) in a
   Bookkeeping section of version 2 (each step's `units` and `input`, in its `source.yaml`; see
   [bookkeeping SPEC](../bookkeeping/SPEC.md)) runs it with `rules test`
   instead of a pytest file. The input manifest is written from that
   declaration, so the reading may be one table or several. That runs the target twice on
   the disposable local stores, each step as its own login, and writes a
   counts-only report:
   ```bash
   uv run --extra mdm python infra/scripts/local-test-stores.py up <store name>
   edgar-warehouse rules test --source <name> --capture <capture folder> \
     --documents <list of document keys> --capture-run <run> --as-of <time> \
     --stores ~/.local/share/edgartools/local-tests/environments/<store name> \
     --out <report.json> [--target <target>] \
     [--fact <name>=<value> ...] [--file <name>=<path> ...]
   uv run --extra mdm python infra/scripts/local-test-stores.py stop <store name>
   ```
   A target that declares `run` takes each fact and file it names, and only
   those (a count, an approved scope; [bookkeeping SPEC](../bookkeeping/SPEC.md)).
   It refuses a store that already holds MDM records: `local-test-stores.py
   copy <new name>` gives a fresh one from the baseline. Invented documents
   need the kind's own shape: a document that carries another kind's
   structural fields (the ones the classification rule tests) is rightly
   held back, so an invented capture proves nothing about the kind. A
   version-1 section is refused: declare each step's units and input first.
   The writer forms units for a read of captured documents (slices, groups
   or each file, with per-document context, a companion file and same-file
   lookups), a read of a combine's pieces, `source.combine`, `mdm.prepare`,
   `mastering.merge` and `journal.record`, and a reading or lookup of another
   source's finished runs, `{run: {source, target, step}}`, which run first
   ([bookkeeping SPEC](../bookkeeping/SPEC.md));
   a target with any other step is refused. The same
   manifest for a real run comes from `edgar-warehouse mdm prepare-capture
   --source <name> --target <target>`, with the same `--fact` and `--file`;
   `edgar-warehouse load` prepares, submits and drives every bundle of a
   capture that way ([data-operations](../data-operations/SKILL.md#load-a-capture)).

   Otherwise, write it as a pytest file that uses the MDM fixtures, and it gets
   its own disposable PostgreSQL 16:
   ```python
   from tests.integration import test_mdm_postgres as core  # its helpers
   # `postgres` starts one postgres:16 container for the session and removes it
   # after; `database` is a migrated MDM database of its own for each test.
   from tests.integration.conftest import database, postgres  # noqa: F401
   ```
   Run it with Docker (check `docker info` answers first), and bound it:
   `timeout -s KILL 600 uv run --no-sync pytest -q -s <file>`.
   `timeout` is GNU's; macOS has none, so there give the run a watcher with
   a deadline instead.
   Where Docker does not start, the same fixtures run on a local
   PostgreSQL 16 that is deleted afterwards:
   `PG16_SERVER=pgserver uv run --no-sync --with pgserver pytest -q -s <file>`
   (`tests/support/pg16.py`). Write in the log which one ran.
   - **Load every source that can bind the same entities.** A rule that
     creates entities is proved with every other source whose records can
     match the same entities (by an identifier or by name) loaded too;
     without them a duplicate cannot appear, and the run proves nothing
     about duplicates.
   - **Measure a known risk before the ruling.** When a ruling carries a
     risk (duplicate entities, links that cannot resolve), count it from
     the captured files first and give the operator the count, not only
     the sentence.
   - **Count the links MDM accepts, not the links a contract writes.** A
     test run shows each record's links; only the Merge Stage shows they
     resolve. Apply a few invented records through the whole chain and the
     Merge Stage first: a link with no stated start, from a publication
     that states no effective time, goes to review.
   - **Configuration first.** Before proposing an engine change, find what
     the rules files already allow (a rule's `on_no_match`, a reading's
     `context`, a reduction's keys or `last`) and put that option to the
     operator, with what it cannot do.
   - **Expect:** under a minute to start the database. A few hundred
     records should finish in under 5 minutes; several thousand take tens
     of minutes. Say the estimate before a long run.
   - **If it hangs or is killed,** its container stays up. List it with
     `docker ps --filter name=edgartools-local-` and remove it with
     `docker rm -f <name>`, or `local-test-stores.py stop <name>` for a stores folder. Remove only the container your run created; the shared store's container stays.
   A full run registers the datasets and policy, applies the bundles, and
   runs a second pass that must change nothing (Examples names one).
3. **The inputs and the proof.**
   - **Input manifest:** a JSON list of `{"member", "sha256", "bytes"}`, one
     entry per captured file, sorted by `member`. Its sha256 is the
     `batch_hash`. For a bronze capture with a `receipts.jsonl` (one line
     per file: key, sha256, bytes), use the sha256 of that file.
     The manifest lists exactly the files the test read: the feed's own, and
     a file another source captured when the reading joins it (a Name Matching,
     another feed's catalog), since the counts depend on it. A
     `receipts.jsonl` that names a file the test did not read, or misses one
     it did, is then not the manifest: write one with exactly those files.
   - **Digest, before saving:**
     `from edgar_warehouse.bookkeeping.clean.config import digest`. Then
     `digest(files.load_source(Path("rules/sources/<source>/source.yaml")))`
     for a source, or `digest(files.policy())` for the merge rules. It is
     what `rules save` will store.
   - **Proof file:** JSON with `digest`, `batch_hash`, `passed`, `evidence`
     and `note`. `--proof-uri` is `file://<absolute path>` locally or
     `s3://…`, and `--proof-sha256` is the file's sha256.
   - **Version label:** `<source or kind>-<YYYY-MM-DD>.<short change name>`,
     e.g. `acme.registry-2026-09-30.first`.
4. **Save and record the test run:**
   ```bash
   edgar-warehouse rules save --source <name> --version <v> rules/sources/<source>/source.yaml
   edgar-warehouse rules record-proof --source <name> --version <v> --proof-uri <uri> --proof-sha256 <sha256>
   ```
   The proof names:
   - the version's `digest`;
   - the input `batch_hash` (the captured files' manifest sha256);
   - whether it `passed`;
   - `evidence` (the counts and up to 10 examples);
   - a one-line `note`.

   A failing run is recorded too; it can be replaced until it is approved.

   **A source tested with `rules test`** records its run itself: save the
   version first, then add `--version <v>` to the `rules test` command, using
   the operator's Rules Database connection from the central section above.
   The run is checked before it starts: the saved version must
   be the rules on disk. Its proof is the report's counts, and its
   `batch_hash` the first pass's input manifest. A source that declares
   `acquisition` records its test run the same way: the run switches on its
   pipes over files already captured. Its live acquisition is switched on
   apart, with a real acquisition run's evidence (`record-proof`).

   The merge rules are one document, `platform`, saved whole from
   `rules/merge/policy.yaml` (the kind files beside it come too):
   ```bash
   edgar-warehouse rules save --merge platform --version <v> rules/merge/policy.yaml
   edgar-warehouse rules record-proof --merge platform --version <v> --proof-uri <uri> --proof-sha256 <sha256>
   ```

**A new domain: the order of approvals.** Each step needs the one before it:
1. Measure the classification rule's proof on this source.
   - **The sample:** records drawn at random from the files, each labelled
     by hand against the kind's written definition (its spec's rule). Record who labelled them.
   - **The bar:** `bars.classification` (`min_precision`,
     `one_sided_confidence`). With every record correct, the Wilson lower
     bound is `n / (n + z²)`, so the least sample is
     `n ≥ p·z² / (1 − p)`. For example, 0.99 at 0.975 confidence
     (z = 1.96) needs 381; 0.95 at 0.95 (z = 1.645) needs 52.
   - **Record it** in `rules/merge/pending-proofs.yaml` under the rule's id,
     in the shape of the entries there: `method`, `one_sided_confidence`,
     `n`, `correct`, `lower_bound`, `adversarial` (`fixture_sha256`,
     `violations`), `cohort` (`files`: the sha256 of each input and
     script; `by_step`: a sample of its own per step of a rule with
     several), `approved_by: null`, `approved_at: null` and a one-line
     `reason`. Switch-on recomputes the bound from `n` and `correct`:
     write it cut to six places, never rounded up (the stated bound may
     not exceed the recomputed one, and must be within 0.00001 of it).
     The adversarial fixture holds pairs the rule must never join (a hard
     veto says they differ); `violations` counts those it joined, and
     must be 0.
2. The operator switches on the classification rule, then the identifier
   matching rule (APPROVE.md, "Switch one declared matching rule on").
3. Save, prove, approve and activate the merge rules (`--merge platform`).
4. Then test, approve and activate the source version. Its records now
   classify and match.
