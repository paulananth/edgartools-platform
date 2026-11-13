# Under what exact conditions may a live production load be submitted, and who authorizes it?

Type: grilling
Status: open
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
