# Used swap is not pressure: the scheduler started nothing on a machine with memory to spare

Status: resolved
Type: task

Seen 2026-11-18 on the second hosted load, restarted onto the operator's two-hour deadline ("2 hours"): the scheduler logged its projection
and then started nothing for three minutes with no step running.

## Findings (five whys, from the machine and the code)

- `machine_pressure` read `vm.swapusage` and called anything over three quarters of swap "high"; a high level starts nothing.
- Swap was 85% used (3.5 of 4 GB) while 56% of memory was free: macOS keeps swap in use long after the pages that filled it have gone.
- Swap used is a stock that records what happened earlier; only memory free (and the rate of swapping) says the machine is pressed now.
- The same rule had also stopped the first scheduler from raising workers ("low" needs under half the swap used).

## Parts

- [x] `pressure` takes the memory free: used swap presses only when memory is short (under a quarter) or unreadable, under a tenth of
  memory free presses whatever the swap, and "low" needs half the swap or four tenths of memory free (2026-11-18 12:02 ET;
  `test_full_swap_with_memory_to_spare_is_not_pressure_and_a_short_memory_is`: main's rule returns `high` for swap 85% with 56% of memory free, where the test expects `low` (the keyword `memory_free` did not exist: `TypeError`);
  live: the restarted scheduler started both lanes' first steps within a minute)
- [x] `has_headroom`, which kept the old swap-only rule and which nothing called, is deleted with its test; the memory edges of the rule are tested (2026-11-18 12:04 ET; `test_the_memory_edges_of_pressure`)
- [x] The runbooks and the skill say it (daily-run, init, data-operations "Start with live state") (2026-11-18 12:04 ET; read in the PR)
- [x] `machine_pressure` reads `memory_pressure` beside `vm.swapusage` (2026-11-18 12:02 ET; the live restart above)
- [x] Learning → skill: data-operations (the scheduler's rule says "memory free, with swap only beside it") (2026-11-18 12:02 ET; the SKILL.md and runbook sentences read in the PR)
