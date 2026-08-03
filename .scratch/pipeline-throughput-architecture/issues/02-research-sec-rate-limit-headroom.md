Type: research
Status: resolved

## Question

What is the real, safe headroom for increasing parallelism against SEC
EDGAR before hitting rate-limit throttling or blocking -- as a hard input
constraint on tickets 03 and 04?

Specifically:
- SEC's documented per-IP rate limit (currently assumed ~10 req/sec in
  CLAUDE.md's "Key invariants" section) -- confirm current published
  guidance and any burst/short-window allowance.
- Current in-process limiter: `sec_client.py`'s `pyrate_limiter` bucket,
  9 req/sec per ECS task.
- Whether ECS tasks running concurrently (e.g. `BOOTSTRAP_BATCH_CONCURRENCY`
  2-5 today) share a single outbound IP (NAT gateway) or get distinct
  IPs -- this determines whether task-count parallelism and intra-task
  concurrency compete for the same 10 req/sec ceiling or not. Check the
  actual VPC/NAT Terraform config (`infra/terraform/accounts/prod/`)
  rather than assuming.
- Whether SEC's guidance distinguishes bulk/bot traffic patterns that
  would make aggressive parallelism (even under the numeric limit) a
  ToS/blocking risk regardless of raw req/sec math.

## Done when

A short, cited answer (SEC's own published fair-access guidance, plus the
actual NAT/VPC topology from Terraform) that ticket 03 and ticket 04 can
both treat as a hard ceiling when comparing concurrency options.

## Answer

**1. SEC's own published limit (verified live, 2026-08-03, not taken from
CLAUDE.md or any secondary source).**

Fetched directly with `curl -A "EdgarTools Platform Research
thepaulananth@gmail.com" https://www.sec.gov/about/privacy-information`
(HTTP 200; this is the page `sec.gov/search-filings/edgar-search-assistance/
accessing-edgar-data`'s "Fair access" section itself links to as the
authoritative source for "our current rate request limit"). Exact quote:

> "To ensure our website performs well for all users, the SEC monitors the
> frequency of requests for SEC.gov content to ensure automated searches do
> not impact the ability of others to access SEC.gov content. We reserve the
> right to block IP addresses that submit excessive requests. **Current
> guidelines limit users to a total of no more than 10 requests per second,
> regardless of the number of machines used to submit requests.** If a user
> or application submits more than 10 requests per second, further requests
> from the IP address(es) may be limited for a brief period. **Once the rate
> of requests has dropped below the threshold for 10 minutes, the user may
> resume** accessing content on SEC.gov. ... The SEC does not allow
> 'unclassified' bots or automated tools to crawl the site. Any request that
> has been identified as part of an unclassified bot or an automated tool
> outside of the acceptable policy will be managed to ensure fair access for
> all users."
> — https://www.sec.gov/about/privacy-information (fetched 2026-08-03)

The companion page (`accessing-edgar-data`, content dated March 23, 2021,
also fetched live) restates it tersely as "Fair access — Current max request
rate: 10 requests/second" and adds the declared-User-Agent requirement
(already satisfied by this repo's `EDGAR_IDENTITY` env var).

Key findings for tickets 03/04:
- **No burst/short-window allowance is documented anywhere.** It is a flat
  10 req/sec ceiling, not a token-bucket-with-burst or a rolling average
  with headroom.
- **The stated *policy* ceiling is per user/application, explicitly
  "regardless of the number of machines used to submit requests"** — SEC is
  describing one operator's aggregate traffic, not a per-IP entitlement.
  **Enforcement**, however, is IP-address-based blocking ("further requests
  from the IP address(es) may be limited"). This is the exact distinction
  the ticket asked about: staying under 10 req/sec on every individual IP
  does not establish ToS compliance if the *aggregate* traffic from this
  platform's task fleet is understood as "a user or application" running
  bulk/automated searches — SEC's own language treats that as the thing the
  policy exists to constrain, independent of per-IP math.
- **Blocking penalty is non-trivial**: recovery requires the rate to stay
  *below* threshold for a full 10 minutes before access resumes, not an
  instant per-second reset. A brief overshoot risks a 10+ minute stall, not
  a one-second throttle.
- SEC explicitly reserves the right to block "unclassified" bots/automated
  tools regardless of numeric compliance — orthogonal to the req/sec math
  entirely.

**2. Current in-process limiter (`edgar_warehouse/infrastructure/sec_client.py`).**

```python
def _create_sec_rate_limiter() -> Limiter:
    # 9 req/sec matches EDGAR_RATE_LIMIT_PER_SEC (edgartools default).
    # In-process only — does not coordinate across ECS tasks.
    rate = Rate(9, Duration.SECOND)
    bucket = InMemoryBucket([rate])
    ...
```
(`sec_client.py:26-34`, `Limiter.try_acquire` called at line 67 in
`download_sec_bytes`, once per SEC HTTP request.)

Confirmed: **9 req/sec is a hardcoded Python literal**, not an env var —
`EDGAR_RATE_LIMIT_PER_SEC` never appears as an actual `os.environ` read
anywhere in this repo (`grep -rn "EDGAR_RATE_LIMIT_PER_SEC"` across all
`*.py` only matches this comment and one other comment in
`warehouse_orchestrator.py:3347` referencing it). The name in the comment is
naming the `edgartools` PyPI package's own internal default that `9` was
chosen to match, not a locally configurable knob — there is currently no way
to tune this per-task rate without editing this literal.

**3. CLAUDE.md's "~10 req/sec" reference — not independently cited in
CLAUDE.md itself.**

`CLAUDE.md:814-817` ("Key invariants") asserts "SEC's 10 req/sec per-IP
limit" as a bare claim with no link or citation attached, and frames it as
**per-IP** rather than per-user/application. Per finding #1 above, that
per-IP framing is not quite what SEC's own text says (SEC states the ceiling
"regardless of the number of machines used" — i.e., intended as an
aggregate-per-operator limit; only the *enforcement* mechanism is per-IP).
The numeric value (10) is correct and now independently confirmed against
the live SEC page; the "per-IP" characterization is the part CLAUDE.md
should be treated as approximate on, not authoritative.

**4. NAT/VPC topology — confirmed from Terraform, not assumed.**

`infra/terraform/modules/network_runtime/main.tf` (used by
`infra/terraform/accounts/prod/main.tf:21`, `module "network_runtime"`) has
**no NAT gateway at all** — no `aws_nat_gateway` resource exists anywhere in
`infra/terraform/accounts/prod/` or the module it sources (confirmed via
`grep -rn nat_gateway`/`grep -rln aws_nat_gateway` returning zero hits in
that tree). The module provisions only:
- `aws_vpc.this`
- `aws_internet_gateway.this`
- `aws_subnet.public` (`map_public_ip_on_launch = true`)
- `aws_route_table.public` with a `0.0.0.0/0 → igw` route
- `aws_security_group.ecs_public_tasks` (outbound-only)

There are no private subnets and no `aws_nat_gateway`/`aws_eip` for NAT
anywhere in this module or `accounts/prod`.

Every ECS `RunTask` state built by `infra/scripts/deploy-aws-application.sh`
(6 occurrences: e.g. lines 1338-1344, 1425-1431, 1558-1564, 1668-1674,
2402-2408, 2967-2973) sets:
```json
"NetworkConfiguration": {
  "AwsvpcConfiguration": {
    "AssignPublicIp": "ENABLED",
    "SecurityGroups": security_groups,
    "Subnets": subnets
  }
}
```
Subnets are resolved to the `${NAME_PREFIX}-public-*` subnets (deploy
script, ~line 668). Combined with Fargate `awsvpc` networking, **each ECS
task's own ENI receives a distinct public IP directly** (standard AWS
Fargate behavior when `AssignPublicIp=ENABLED` in a public subnet with an
IGW route, and consistent with there being no NAT gateway to route through
in the first place) — **tasks do not share a single outbound IP.**

**Answer to the ticket's core topology question: concurrent ECS tasks get
distinct public IPs, not a shared NAT IP.** This means, from SEC's
*enforcement* mechanism (per-IP blocking), task-count parallelism
(`BOOTSTRAP_BATCH_CONCURRENCY`) and intra-task concurrency are **not**
drawing down the same per-IP throttle bucket — each task's 9 req/sec
in-process limiter is independent at the IP level. However, per finding #1,
this does **not** mean the two axes are unconstrained relative to each
other: SEC's stated *policy* ceiling is aggregate-per-operator regardless of
machine count, so N concurrent tasks × 9 req/sec each is still N×9 req/sec
of traffic identifiable as coming from one operator (same declared
`EDGAR_IDENTITY` User-Agent across all tasks), which is the exact
bulk/automated-traffic pattern the fair-access policy exists to flag —
independent-IP enforcement reduces the odds of a single IP tripping the
per-IP block, but does not establish that aggregate multi-task fan-out is
within the spirit of the "10 requests/second, regardless of the number of
machines used" policy language.

**Hard ceiling for tickets 03/04 to treat as given:**
- SEC's documented, enforced ceiling: **10 req/sec**, no burst allowance,
  10-minute cooldown on violation, per https://www.sec.gov/about/privacy-information.
- Current in-process per-task limiter: **9 req/sec, hardcoded**
  (`sec_client.py:29`), already just under the documented ceiling on a
  *single* task.
- ECS tasks get **distinct public IPs** (no shared NAT) — per-IP blocking
  enforcement is independent per task, so raw per-IP math alone does not
  force serialization across tasks.
- But SEC's own policy text frames the 10 req/sec ceiling as
  per-user/application "regardless of the number of machines used" — so
  any concurrency design that runs N tasks at ~9 req/sec each (N≥2) is,
  by SEC's own stated policy language, already over the documented
  aggregate ceiling for a single declared identity, even though today's
  distinct-IP topology means it is unlikely to trip the *IP-based
  enforcement* mechanism at low N. Tickets 03/04 should treat "9 req/sec
  per task, independent per-IP enforcement" as the hard technical ceiling,
  and treat "10 req/sec aggregate regardless of machine count" as the
  stated ToS boundary that increasing task-count parallelism edges past
  by design, not as a hypothetical risk.
