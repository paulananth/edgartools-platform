# 01: A tile click filters the lane board

Status: resolved
Type: task
Owner: claude (operator, 2026-11-26: "for the grafana make it dynamic wheh i click on running it should filter out running, same for done and stalled")

## Checklist

- [x] Test first: `test_a_tile_click_filters_the_lanes_to_the_states_it_counts` failed with `KeyError: 'templating'` (the board had no filter), passes after (2026-11-26 20:30 ET)
- [x] One list of filters in `design.py` (`FILTERS`): each tile counts with its filter's pattern and links to it, the Steps list offers every filter with All chosen, and the lane board keeps the steps whose state at the end of the time range matches (`@ end()`) (2026-11-26 20:30 ET)
- [x] Live check on the running load's Prometheus: the rows the lane query keeps equal each tile's count: All 30, Running 5, Done 18, Stalled or locked 1, Failed 0 (2026-11-26 20:30 ET)
- [x] Pushed to the local Grafana (HTTP 200); the read-back has the `state` variable and each tile's link (2026-11-26 20:30 ET)
- [x] Learning → skill: `load-monitoring/SKILL.md`, the interactions table (a tile click filters the lanes; a tile counts with the states it filters) (2026-11-26 20:30 ET)
