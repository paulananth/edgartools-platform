# Ordered name projection review — 2026-10-08 18:14 ET

## Spec

Independent reviewer found no scoped projection blocker and reran the two
projection/census test files: 97 passed in 18.24s. Category/LEI/key/wanted
registration/other-name read order and typed normalization are preserved.
The synthetic reduction test expresses intended last-timestamp and holder
subtraction semantics in test Python; it does not prove an implemented generic
reducer. Deliberate faults are synthetic. Captured prefix rows prove parity,
not captured fault qualification or original archive EOF. Whole-source,
cascade, installed population and active caller replacement remain open.

## Standards and GoF

Initial review found prohibited YAML anchors hidden by yaml.safe_load in tests.
Fixed recipe serialization with files.dumps, test loading with files.load,
and canonical-transform equality coverage. Final review found the imported
qualification helper absent from runtime pins. Added the helper module and
reran the captured report successfully with unchanged before/after pins.
No remaining scoped blocker from static review; reviewer did not rerun the
full native/affected suites. Parent ran 146 native and 134 affected Python
checks successfully. Preserve interpreter/functions; no GoF hierarchy warranted.

## Ownership gate

Before commit/push, the mandatory overlap guard found Claude worktree
`edgartools-platform-claude-skills-generic-2`, branch
`claude/skills-generic-bookkeeping`, also changing
`skills/data-platform/READING.md`. This was the historical checkpoint status:
the ownership question was pending, and 13cd3d23 was the pushed head.
The synchronization section below records resolution after refreshed evidence.

## Lookup integration review — 2026-10-08 18:27 ET

Both reviewers found no scoped blocker. Spec independently ran 94 lookup,
stream and combination checks in 3.21s. Parent gate: 207 affected checks pass
in 41.99s; native grammar unchanged since the 146-test gate. Standards identified
control_contract.py and bookkeeping/clean/config.py missing from the worker's
runtime pins; added both and reran successful captured worker qualification.
The captured report records worker receipt hashes, 1,000 records, table counts,
unchanged retry and replay verification, with separate-process/full-source/
cascade/installed/full-goal flags false. Publication_count and wanted values
still require independently proven complete upstream derivation.

The old overlap observation was taken against stale references across two
repositories. #876 is now merged and its Claude worktree is clean. The temporary
cross-repository guard wrapper now imports foreign refs read-only into the owned
bare repository, prevalidates all compared commits, and compares against the
same freshly fetched main commit. Do not accept a guard's empty overlap list
when Git comparison errors occur; process substitutions can hide those errors.
Final guard result must be captured before any commit/push.

## Synchronization and documentation — 2026-10-08 18:34 ET

After #876 merged, the refreshed guard against 40741eed passed with validated
foreign references and no Git comparison errors. The earlier ownership question
is no longer a commit gate: the Claude worktree is clean and its changes match
main. Checkpoint 70c1c410 preserved all WIP before rebasing; the owned two commits
are now cf418c98 and 34b7dacc. The only conflict was the generic predicate example
in READING.md. Kept main's code example and inserted the empty iteration grammar.
265 affected plus genericity checks pass in 71.12s; indexed receipt documentation
then passed 91 affected/genericity checks in 3.78s. No retirement completion claim.

## Incremental traversal review — 2026-10-08 18:45 ET

The spec reviewer independently ran 11 initial traversal tests (5.60s) and
found no scoped blocker. The standards reviewer reproduced a mutable-index
defect: editing yielded future receipts could redirect suspended traversal.
Fixed by isolating the private authenticated index from each yielded snapshot;
regression tests mutate both returned index and chunk metadata. The reviewer
reran the reproduction and confirmed original rows/evidence are retained.

The standards reviewer also identified the new index cap unintentionally
tightening legacy materialized loading. Restored the caller's existing limit
for load; only iter_load uses the 32 MiB cap. An actual larger inline JSON
regression proves compatibility. Final targeted/genericity gate: 151 passed
in 17.26s. Both reviewers found no remaining scoped blocking finding.

The full index is copied for each yielded partition. This keeps ownership
isolation simple but has partition-count times index-size cost. Measure it
before full-source qualification; it is recorded as unfinished rather than
asserting bounded memory also proves acceptable runtime. Generators/plain
functions remain justified by the GoF review; no hierarchy is added.

Traversal prefixes remain provisional, and the iterator publishes nothing.
The actual reducer must exhaust successfully before any write. Full configured
reduction, cascade, complete upstream population, original EOF, installed
population and executable-caller retirement remain incomplete.

Final broader gate after both review fixes: 279 passed in 37.39s. Fresh
captured qualification passes 1,000-record worker execute/retry/replay and
incremental-consumer parity with identical before/after runtime pins. Original
source EOF, separate processes, cascade and installed population remain false.

## Measured traversal revision and full-CI findings — 2026-10-08 19:07 ET

The ownership-copy cost measured 101.90s at 2,048 partitions and 461.36s at
4,096. Revised the new event API before release: the header pins the complete
original reading, while chunks copy only current-range and source evidence.
Both independent reviewers inspected the revision and found no scoped blocker.
Tests cover returned header/chunk and caller-reference mutations. The repeatable
committed harness verifies row/byte/identity accounting and stable runtime pins,
with 4,096 partitions taking 2.14s in one synthetic trial. This is not original
archive EOF, worker production qualification, or a statistical speedup claim.

Initial CI caught an architecture violation missed by focused tests: the worker
imported control config solely to pin its dependency file. Removed the import
and retained the file pin independently. A decoder-path regression then proved
the dependency path must be captured at load time; repaired without weakening
the test. CI also caught a changed version-2 error diagnostic; restored the
version label while retaining exact version-3 shape checks. Final affected plus
architecture-control/context gate: 314 passed in 55.31s. Full CI must rerun.

Captured-prefix worker verification now also checks the incremental header's
original reading and contract receipts. Fresh qualification passes unchanged
runtime/input pins, exact projection rows, retry and replay. All broader scope
flags remain false. The remaining local architecture environment failures were
missing jq and unwritable Darwin mktemp paths; external test-tool configuration
resolved them without repository production or assertion changes.

## Bounded complete-set reduction review — 2026-10-08 19:29 ET

### Spec

Initial independent review passed 25 new tests, then reproduced a generic
union-order bug: one versus two partitions changed a last value across two
tables. Fixed by rejecting last on table unions before reading. Reviewer ran
three targeted cases and confirmed both layouts refuse and union subtraction
passes. The bundled recipe unions aliases/transliterated members, subtracts
complete legal membership, and reads timestamps from one ordered table.
No scoped blocker remains. Complete population/cascade/installed gates remain
open; this is not a full census construction or retirement claim.

### Standards and GoF

Add the artifact codec dependency pin without a forbidden control import.
Check output cardinality before key sorting and use bounded heap selection for
capped samples. All findings addressed; reviewer reports no scoped blocker.
Keep plain functions, generic named contracts and existing worker registry.
State payload bytes are not RSS; separate key/member cardinality bounds govern
object overhead. Legacy combiner byte-limit monkeypatch regression remains
independently failing after restoring dynamic default lookup.

Parent verification: 343 affected/context/genericity/control checks passed in
32.45s. Final hash-pinned captured-prefix worker/reducer qualifier passes exact
independent-oracle rows, verification, unchanged retry and original scope
identity. Runtime pins agree before/after; source EOF, separate processes,
cascade and installed population remain unqualified. An earlier qualifier run
correctly refused when runtime files changed during review repairs; no result
from that refused run is counted.
