# Data Catalog for Person and links

Type: grilling (HITL)
Status: resolved
Blocked by: 02

## Question

`rules catalog` publishes one way to OpenMetadata (rules skill 13). The local catalog stack was removed on 2026-10-01, and its volumes on 2026-10-02 (backup in `~/.local/share/edgartools/db-backups-20261002/`).

Decide:
- whether the catalog stack comes back locally, and when;
- whether the catalog and the Mapping Documents must show Person and the relationship types before switch-on.

## Answer

Operator, 2026-10-02 by 11:49 ET: "Both before switch-on".

Before Person feed 1 is switched on (ticket 12), both of these must show Person and the Forms 3/4/5 and GLEIF link types:
- the Mapping Documents;
- the local OpenMetadata catalog.

That means the local stack is restored from `~/.local/share/edgartools/db-backups-20261002/` (or recreated clean), and the catalog is republished with `rules catalog`. The build is ticket 19.
