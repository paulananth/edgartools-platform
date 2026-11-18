# One stores file, one connection URL per login

Status: open
Type: task

Operator, 2026-11-18: "you cannot have 64 connection string kiss please"; asked how, chose "One file, one URL per login".

The hosted stores folder holds 33 connection strings for 9 logins across `connection.env`, `worker.env`, `governance.env` and `reader.env`: a login repeats under a different variable name for each duty. A review once printed them, each twice.
Do this after the fresh load (ticket 238) finishes; the running lanes read the folder as it is.

## Parts

- [ ] Inventory every command that reads a store's connection variable (`MDM_DATABASE_URL`, `*_MIGRATION_DATABASE_URL`,
  `MDM_REGISTRATION_DATABASE_URL` and the rest) and which login each needs
- [ ] One `stores.env`: 9 logins, 9 URLs, each named for its login and never repeated; `load --stores` and the commands
  pick a login by name (a test that fails while a command still needs a repeated URL)
- [ ] The local test server writes the same file, so local and hosted match
- [ ] `provision_hosted_store.py` reads and writes it; the runbook's initialize steps and the connection section of the
  data-platform skill say it once
- [ ] A guard: a command's output and a reviewer's view show a login's name and never its URL
- [ ] Learning → skill
