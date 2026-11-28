# One hosted load, then Gold acceptance

Status: open
Type: task
Owner: claude (map decision 15)
Blocked by: 02, 03, 04, 05, 06

## Checklist

- [ ] On the hosted RDM before the load: `scripts/dev/reload_rdm.py` publishes `sec-cover-exchange` version 1 (from ticket 04), so the mirror carries it in `rdm.published_code`
- [ ] Before the load, the silver owner runs `bash infra/scripts/deploy-silver.sh <stores>`: it records the 17 specs ticket 06 relinked (their tables keep their rows; a load stops on a table whose recorded spec differs) and registers `set_aside`, which Gold's link tests read
- [ ] The two Gold CIKs the company feed never saw: traced
- [ ] One hosted load: the company feed under the new rule, the OpenFIGI input, the finish, the mirror's refresh
- [ ] `dbt build` (new views) and `dbt test` as the Gold writer: every link test passes
- [ ] "Gold accepted" ticked in hosted-mirroring 23 and hosted-load-aws 01
- [ ] Learning → skill
