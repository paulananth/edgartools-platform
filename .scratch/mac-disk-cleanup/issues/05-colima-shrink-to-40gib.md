# Colima disk allocation

Type: task
Status: resolved
Blocked by: 03

## Question

Shrink Colima disk from 80 GiB (later revised to 40 GiB, then **20 GiB** by user).

## Answer

2026-08-07:

1. `colima stop` (already stopped)
2. `colima delete -f -d` — removed ~11 GB host data; free space jumped ~11 → **24 GB**
3. `colima start --cpu 4 --memory 8 --disk 20 --arch x86_64`

Verified:

```
PROFILE    STATUS     ARCH      CPUS    MEMORY    DISK     RUNTIME
default    Running    x86_64    4       8GiB      20GiB    docker
```

`~/.colima/default/colima.yaml` has `disk: 20`.  
Host `~/.colima` actual use: **~1.1 GB** (was ~11 GB).

**Side effect:** all Docker images/containers wiped (fresh VM). Image prune (ticket C) is N/A — image list empty.
