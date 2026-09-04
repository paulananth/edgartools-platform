# Prototype end-to-end incremental acceptance evidence

Type: prototype
Status: resolved
Blocked by: 05, 06, 07, 08, 09, 10

## Question

What concrete evidence artifact and test matrix prove the implemented pipeline
propagates only required changes and still converges correctly end to end?

Prototype a versioned, secret-safe acceptance schema covering no-op replay,
modified-key propagation, `RETIRE`, `SCOPE_COMPLETE`, concurrent producers,
partial load/resume, out-of-order delivery, repair attestation, bounded MDM
closure, gold affected-DAG selection, unchanged graph-partition reuse, full
graph verification/activation, reconciliation backstop, and an aligned Decision
Watermark. It must record selected/processed/skipped keys and costs so success
cannot be inferred from row counts or clean logs alone.

## Answer

Built `edgar_warehouse/acquisition/acceptance_evidence.py`: an
`AcceptanceEvidence` schema (versioned via `schema_version`, secret-safe by
a locked field set — references/hashes/enums/counts/durations only) with a
fail-closed constructor, `build_acceptance_evidence`, that downgrades a
caller's `passed=True` claim whenever the record touches zero keys or
carries any reason. `unavailable()` is a separate, honest state for a
scenario this map has designed but has no live evidence source for yet.

Four adapters bind existing, already-proven evidence onto this schema
without re-deriving any stage's correctness logic: `from_content_impact`
(Tickets 03/18), `from_expected_producer_status` (Ticket 19),
`from_parity_verdict` (Ticket 51/53), `from_cause_alignment` (Ticket 41).
Full per-scenario trace, including 3 scenarios proven by a shape (an
exception, an ordering property, an immutable child revision) this
prototype deliberately did not force into the schema, 2 scenarios honestly
`unavailable()` (Tickets 49/50, confirmed unbuilt), and 3 scenarios
(RETIRE, gold affected-DAG, graph-partition reuse, full graph
verification/activation) with real evidence but no adapter yet:
[assets/acceptance-evidence-scenarios.md](../assets/acceptance-evidence-scenarios.md).

18 tests (`tests/acquisition/test_acceptance_evidence.py`), including the
ticket's own core requirement —
`test_success_cannot_be_inferred_from_a_clean_but_empty_record` — plus the
secret-safety field-lock test. Full `tests/acquisition/` +
`tests/serving/` suite green. `/gof-refactor-reviewer` consulted before
creating the module (Rule 0: new code responding to a real, evidenced
requirement, binding rather than duplicating existing logic — proceed).

`/code-review`'s three axes (Standards, Spec, GoF) found Standards and GoF
clean; Spec caught two real issues, both fixed: `from_parity_verdict` was
silently dropping `only_gated` keys (a real, expected case per Ticket
51/53's own "equal-or-superset" semantics) instead of counting them as
processed — fixed with a regression test
(`test_from_parity_verdict_counts_only_gated_keys_as_processed`); and the
trace doc overclaimed scenario 12 (full graph verification/activation) as
"Bound" when `from_cause_alignment` only ever tags its output
`DECISION_WATERMARK_ALIGNMENT` — corrected to "Traced, not adapted."

While resolving this, confirmed Tickets 49 and 50 (bounded MDM closure,
reconciliation backstop) are genuinely unbuilt — both lack the standard
`Type:`/`Status:` header other tickets use, which is why an earlier
`/wayfinder` inventory this session silently omitted them from its
open/claimed report. Flagged in the trace asset so a future survey of this
map doesn't repeat the miss.
