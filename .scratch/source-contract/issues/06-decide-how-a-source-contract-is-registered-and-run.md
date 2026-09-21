# Decide how a Source Contract is registered and run

Type: grilling
Status: open
Blocked by: 01

## Question

Check 1 fails if a new source needs its own orchestration stage. Decide:

- where Source Contracts live (`sources/<name>/`?) and how the engine
  discovers them;
- how a contract version is registered (alongside Clean MDM's source
  registry and `store.register_policy`, not a competing registry);
- how one generic stage runs every registered contract over new Bronze
  Artifacts and publishes to Clean MDM as a pinned source publication;
- what the one local command (`source check`) does and does not share with
  that stage.
