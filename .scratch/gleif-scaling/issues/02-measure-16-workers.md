# Measure GLEIF at 16 workers on compute that carries them

Status: open
Type: task

Split from `01-can-gleif-run-16-workers.md`. Sixteen workers hold about 6 GB and use about 3 cores (each held 324 to 421 MB
and used 15 to 20% of a core, waiting on round trips to the database). Neither this 8 GB Mac nor a 2 vCPU task carries them.

## Parts

- [ ] A task with about 6 GB and 3 or more vCPUs runs the GLEIF merge at 16 workers beside a run at 8, and the minutes of each
  are recorded: whether the merge is shorter
- [ ] Learning → skill: data-operations, the workers a step can carry, with the measured memory and the result
