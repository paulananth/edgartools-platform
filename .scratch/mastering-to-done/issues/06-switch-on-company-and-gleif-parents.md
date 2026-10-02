# Switch on Company and the GLEIF parents

Type: grilling (HITL)
Status: open
Blocked by: 02, 04, 05, 13

## Question

Where and in what order do the approved versions get switched on (`rules activate`)?

- **The target:** a fresh local Clean MDM database to create and migrate (`mdm migrate`). Which port and container name, and is it kept as the operator's store?
- **The order:** Company first, then the GLEIF accounting parents. Person comes later, in ticket 12.
- **Proof before each switch-on:** the run on captured bronze that the operator reads first.

## Carried in

- Review finding 5, from ticket 05: build the GLEIF batches by bytes, under the 16 MiB save cap. Measure a 1,000-record batch after the #772 fix first; it was 43 MB in ticket 27.
- D5, from ticket 02: whether link ends stop the closure, measured at full GLEIF scale.
- Ticket 04: prove `rules run --target mdm` end to end on this run.
