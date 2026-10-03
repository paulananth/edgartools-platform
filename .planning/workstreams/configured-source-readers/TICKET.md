# Configured source readers

Continue ticket 21's full Company/Person/GLEIF equivalence and installed empty-store proof. This branch starts with the generic parallel-array iteration needed by raw SEC submissions. No reader is retired before equivalent behavior is verified.

- [ ] Review engine and loader history with GoF; retain the existing function-based design.
- [ ] Add bounded parallel-array record iteration with explicit length handling and strict contract validation.
- [ ] Verify alignment, optional arrays, empty input, malformed shapes, limits and deferred raw evidence.
- [ ] Compare configured filing projections against the old loader on pinned captured data.
- [ ] Document the grammar and verify Python/installed-worker exposure.
- [ ] Open a dependent PR; verify all CI suites and aggregate gate.
- [ ] Company read block, scalar/classification/address/grouping equivalence, then reader/loaders retirement.
- [ ] Person read block and equivalence.
- [ ] GLEIF read block and all positive/failure equivalence, then reader retirement.
- [ ] Installed empty-store full proof: 6,414 Companies, 3,052 CIK+LEI, unchanged replay.

## Design review

Engine/loader history confirms parallel-array expansion is currently source-specific. Add one generic record-selection function, retaining existing expression evaluation and record checks. No new GoF class hierarchy is justified. Array alignment policies are explicit contract data, never inferred from a feed name.
