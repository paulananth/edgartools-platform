# Grafana on the Mac reads the load running on AWS

Status: open
Type: task
Owner: claude (operator, 2026-11-27: "do option 2 on its own branch")

The operator asked "can the prometiuse send the status to local mac grafana". Prometheus pulls, and the Mac has no
address AWS can reach, so the Mac's Prometheus reads the task: option 2 of the two offered (the task runs the exporter,
its port open to the Mac's public address only, the launch script names the task's address to the Mac's Prometheus).

## Checklist

- [x] The load task runs the load monitor's exporter beside the worker, sharing the task's processes (`pid_mode = "task"`): `terraform validate` (2026-11-27 15:35 ET)
- [x] A security group opens the exporter's port to the Mac's public address only (`metrics_cidr`, a /32; null opens nothing): `terraform validate` (2026-11-27 15:35 ET)
- [x] Prometheus reads one exporter named in a file on a named volume (no host path); `monitoring.py target` names it: `test_prometheus_reads_the_one_exporter_named_in_its_target_file`, `test_status_reads_an_aws_target_without_asking_for_the_macs_exporter` (2026-11-27 15:35 ET)
- [x] `aws-load.sh` names the task's exporter once the worker runs and this Mac's again when it ends; the monitor never stops a load (an unread Mac address opens nothing; a failed lookup of the task's address leaves Grafana on the Mac): `bash -n`, the empty option list checked under `set -u` in bash 3.2 (2026-11-27 15:35 ET)
- [x] Tests and `terraform validate`: load monitoring 21 passed, `terraform validate` Success (2026-11-27 15:35 ET)
- [x] Live: Prometheus follows the target file both ways: after `target 192.0.2.10:9108` its active target was that address (down, nothing there), after `target` the Mac's (up) (2026-11-27 15:35 ET)
- [x] The apply refused the security group: AWS allows no apostrophe in a group or rule description (`"ingress.0.description" doesn't comply with restrictions`); both descriptions now pass its pattern, checked against it (2026-11-27 17:14 ET)
- [x] `aws-load.sh` runs the monitor through `uv run`: the Mac's `python3` (3.9) refused `monitoring.py` (`TypeError: unsupported operand type(s) for |`), so the launch said "monitor: not running" though it ran; the same call through `uv run` named a test address and was put back, live (2026-11-27 17:44 ET)
- [x] Live on AWS: the task's exporter answers the Mac through its port (`load_monitor_up 1`, 14 steps done at the first reading), and Prometheus reads it (2026-11-27 17:44 ET)
- [ ] Live on AWS: Grafana shows the load's running lanes, CPU and memory
- [x] `/code-review` (Standards, Spec, GoF), each on `risky-reviewer`: fixed a test of the compose file's text (deleted) and a fake that matched command text (the target file is now written for real); the monitor no longer stops a load; the port read from Terraform's output; the skill states the port's exposure and how to point Grafana back. Left: `CAPACITY = "local"` in the task, as the worker measures it (2026-11-27 15:35 ET)
- [x] Learning → skill: load-monitoring, "Where the exporter runs" (one exporter at a time, named on a named volume; the AWS task's exporter and its exposure); HOSTED-LOADS, the AWS bullet (2026-11-27 15:35 ET)
