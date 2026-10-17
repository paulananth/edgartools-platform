# Sources run independently

Each source is its own run. The preferred daily order is a convenience, not a
barrier: a delayed source does not stop unrelated sources. Missing required
inputs still block the work that needs them. Unresolved entity links continue
to follow the [source-readiness design](source-readiness.md).

## Check the configuration

```bash
# Check the whole processing inventory and print the available target order.
uv run edgar-warehouse rules sequence check

# Check one source without including its preferred predecessors.
uv run edgar-warehouse rules sequence check --source sec.submissions.person

# Explicitly defer a delayed source; still report the independent sources.
uv run edgar-warehouse rules sequence check --defer gleif
```

`--source` and `--defer` can be repeated. `--file` selects a different sequence
YAML; `--root` selects the Rules directory. The default file is
`<root>/source-sequence.yaml`. Overrides apply only to this check; they do not
edit shared configuration, stop an existing run or alter its frozen inputs.

The JSON report contains an ordered `order` list of structurally configured
targets and a status for each selected source: `configured`, `deferred` or
`blocked`, with reasons. It always says `runtime_readiness: not_checked`.

Exit codes:

- `0`: every selected source has a structurally valid target.
- `2`: invalid sequence or selection, such as a cycle or unknown source.
- `3`: one or more selected sources are deferred or blocked. The independent
  sources remain in `order`; this partial plan is not silently called success.

This command reads local configuration only. It does not contact providers,
connect to a database, submit work, approve rules or verify captured deliveries.
Unknown worker profiles and provider-download targets are excluded from this
local processing plan. Missing target files do not prevent other independent
sources from being checked.

## Two configuration rules

The version-1 file maps source names to exactly three fields:

```yaml
version: 1
sources:
  example.company:
    target: mastering
    requires: []
    after: []
  example.security:
    target: mastering
    requires: [example.company]
    after: []
  example.person:
    target: mastering
    requires: []
    after: [example.company]
```

`requires` means a genuine required source input. Selecting the consumer also
includes these prerequisites, in dependency order. Deferring or blocking a
prerequisite blocks its dependants, including transitive dependants. In this
invented example, deferring Company blocks Security but leaves Person in the
plan.

`after` means preferred ordering when both sources are selected. It does not
include the predecessor when running a source alone and does not block a source
when that predecessor is deferred. Do not turn an optional unresolved issuer
or another waiting relationship into a required source dependency.

Use `target: null` when the source has no source-owned processing target yet.
The report blocks that source explicitly. The committed inventory covers nine
sources: three have existing targets and six have none. All `requires` lists
are currently empty: no new cross-source required-input policy is invented by
this inventory. Existing per-run requirements still apply. The preferred order
is advisory, including the N-PORT order; its producers and required inputs still
need the existing source tickets' implementation and qualification. OpenFIGI
has no committed source document yet and is not added as a runnable source.

## Submit an individual source

The existing independent submission command remains:

```bash
uv run edgar-warehouse rules run --source sec.submissions.person \
  --target mastering --input-manifest "$INPUT_MANIFEST" \
  --input-sha256 "$INPUT_SHA256"
```

Its normal active Rules, authority, input-manifest, worker, verifier and
Bookkeeping requirements still apply. A successful sequence check does not
make this submission succeed or start prerequisites automatically. Separate
worker and verifier processes execute submitted work. Resume uses the existing
run ID and its frozen inputs; a delay is not permission to repin it.

This change implements the offline sequencing check, single-source selection
and deferral plan. It does not implement the common end-to-end source runner,
automatic upstream execution, preparation for the six unconfigured sources or
the [full-delivery and unchanged-repeat acceptance proofs](source-readiness-acceptance.md).
GLEIF's existing target is merge-only. The nine-source readiness audit therefore
remains unchanged; configuration checks are not full-source qualification.
