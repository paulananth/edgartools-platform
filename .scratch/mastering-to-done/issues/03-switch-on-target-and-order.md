# Switch-on target and order

Type: grilling (HITL)
Status: open
Blocked by: none (the Person part waits on 02)

## Question

Where and in what order do the approved versions get switched on (`rules activate`)?

- **The target:** a fresh local Clean MDM database to create and migrate (`mdm migrate`). Which port and container name, and is it kept as the operator's store?
- **The order:** Company, then the GLEIF accounting parents, then Person feed 1 together with its relationship feeds (06, steps 3–4).
- **Proof before each switch-on:** the run on captured bronze that the operator reads first.
