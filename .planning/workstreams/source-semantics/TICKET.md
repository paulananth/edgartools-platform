# Source semantics and reader retirement

Continue the full self-sustaining skill goal from merged #811/#812. Preserve retained readers until configured Company/Person/GLEIF outputs, failures and installed empty-store replay are proved.

- [x] Inspect retained reader failures, native parsing and history; GoF review. Verified current code/history; retain functions and enums, add one focused coercion module rather than a hierarchy; 2026-10-04 07:55 ET.
- [x] Add explicit configured text coercion and parallel shape policies with strict defaults preserved. Verified native acceptance and 61 focused Python tests; 2026-10-04 07:55 ET.
- [x] Reproduce and resolve all six previously recorded filing coercion/shape differences; extend failure and numeric/string oracle coverage. Verified all seven original cases match, 10,000 generated float bit patterns plus 1,000 nested Unicode samples; halfway rounding fault fixed; 2026-10-04 07:55 ET.
- [ ] Compare 18 columns on 1,000 receipt-pinned captures and exercise worker/verifier paths.
- [ ] Document implemented grammar in the bundled skill; independent review and full CI; create PR.
- [ ] Complete configured Company and Person source blocks, reference joins and classification.
- [ ] Complete GLEIF bounded native archive reading, source checks and equivalence.
- [ ] Replace active callers and decommission all retained source parsers after full equivalence.
- [ ] Installed empty-store qualification: 6,414 Companies, 3,052 CIK+LEI and unchanged replay.

No source Rules activation or cloud deployment is included. Existing readers are qualification oracles until retirement is justified.

## Safety and remaining equivalence

`coerce: python` is explicit and generic, implemented in Rust. It retains JSON object order only when requested. Unicode behavior is pinned to the already qualified Python 3.12 / Unicode 15.0 policy. Strict scalar/array/object defaults remain covered. Character expansion is capped before allocation. No loader dependency or source-specific branch is added to control, workers or the engine.

Resolving the original six differences does not prove all malformed source behavior. Empty object fields, zero first-N with invalid unused fields, JSON integers outside the existing finite-number parser range, and nonfinite/surrogate input policies still need an extended refusal audit before reader retirement. Full Company/Person/GLEIF integration remains open.

## Independent review

Spec: no scoped implementation findings. Standards/GoF: no documented violations or structural refactor recommendation; one correctness blocker found. The initial empty-anchor shortcut changed existing `lengths: anchor` behavior without opt-in. Added explicit `on_empty_anchor: ignore_fields` (only with anchor lengths) and a regression proving the default still rejects a null field. The first full local run was deliberately interrupted after 570 passes (112.62s) because its loaded binary and committed installation snapshot predated this correction. It is not final verification.
