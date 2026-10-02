# Switch on Company and the GLEIF parents

Type: grilling (HITL)
Status: open
Blocked by: 02, 04, 05

## Question

Where and in what order do the approved versions get switched on (`rules activate`)?

- **The target:** a fresh local Clean MDM database to create and migrate (`mdm migrate`). Which port and container name, and is it kept as the operator's store?
- **The order:** Company first, then the GLEIF accounting parents. Person comes later, in ticket 12.
- **Proof before each switch-on:** the run on captured bronze that the operator reads first.
