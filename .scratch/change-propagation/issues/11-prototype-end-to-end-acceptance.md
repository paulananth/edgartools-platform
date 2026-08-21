# Prototype end-to-end incremental acceptance evidence

Type: prototype
Status: open
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
