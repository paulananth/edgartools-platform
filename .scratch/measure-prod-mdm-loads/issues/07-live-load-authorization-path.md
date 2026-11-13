# Under what exact conditions may a live production load be submitted, and who authorizes it?

Type: grilling
Status: resolved
Blocked by: 01

## Question

If the hosted qualification and credential gates turn out to be cleared, the plan allows measured
normal production source loads against retained captures — one target at a time, in
source-sequence order, with `--workers 1 --bundles 1`, no `--force`, no `--all`, no
`mdm clear-source`, and no provider request. Each such load is a production data write.

Decide, with the operator:

1. Whether the measurement is retrospective-only by standing preference, or whether live loads are
   in scope at all. The default recommendation is retrospective-only: the environment already
   holds the loads, and a fresh load adds a write without adding a measurement of the original
   timeline.
2. If live loads are in scope, the exact authorization unit: per target, per source, or one
   authorization covering all 16 targets. What the approval statement must name (source, target,
   capture folder, capture run ID, selected document scope) for it to count as approval at the
   point of risk.
3. Whether an approved load may be skipped when normal Change Journal selection yields
   `selected = 0` (everything already processed), and what evidence is recorded instead.
4. The estimate threshold: the plan says report an estimate before any dispatch expected to exceed
   ten minutes. Who receives it and in what form, and is there a dispatch ceiling per session.
5. The retry rule when a load fails or must resume: whether a resumed invocation on a later
   dispatch needs a fresh authorization or rides the original one, and how the run IDs and frozen
   inputs are preserved across it.

Record the resolved rule, and if live loads are out of scope, record that and why. Append a one-line
gist to the map's Decisions so far.

## Answer

Decided 2026-11-13, on the evidence of
[01-hosted-qualification-and-credential-gate.md](../evidence/01-hosted-qualification-and-credential-gate.md).

### The path is closed, and it is closed on evidence, not on preference

No new production source load may be submitted. Both gates are shut:

- **Hosted qualification** — `docs/specs/mdm/acceptance.md:5,120-121` and
  `docs/specs/mdm/state-of-build.md:133-136` defer Snowflake Postgres qualification, and no newer
  approved record exists in the checkout.
- **Credential rotation** — no rotation record exists, and the live private environment files still
  carry the unrotated credential set (every credential-bearing value is byte-identical to
  `governance.env.before-reset-20261112`).

### The rules, so that reopening is mechanical

1. **The measurement is retrospective-only.** The report is built from retained evidence. No
   production write, no MDM/Postgres connection, no provider request, no capture target.
2. **A live load becomes permissible only when both gates clear.** The gate check is: a newer
   approved qualification record naming `EDGARTOOLS_PROD_MDM` as a qualified target, **and**
   credential-rotation evidence plus private environment files whose credential fingerprints
   differ from `governance.env.before-reset-20261112`. Either one alone is not enough.
3. **The authorization unit, if that happens, is one target at a time.** An approval names the exact
   source, target, retained capture folder, capture run id, and the selected document scope. It
   covers that one invocation only; a second target needs its own approval.
4. **A resumed invocation rides its original approval** when the run id and the frozen inputs are
   unchanged. Changed inputs or a changed rules version make it a new approval.
5. **`selected = 0` is not a failure.** If normal Change Journal selection yields no documents, no
   run is submitted; the row records `selected: 0` and the already-processed count, and the
   historical timing stands.
6. **The ten-minute estimate is reported before the dispatch**, with the target, the estimate and
   the expected bundles.
7. **No competing run over the same resources.** One target at a time, in source-sequence order,
   then the three link targets ahead of their consumers.

### Why no dispatch is authorized in this session

The plan's own condition — "If no newer approved hosted evidence is found, stop before new
production writes and finish the retrospective report only" — is met. The ticket's rule 2 is the
test, and the test fails.
