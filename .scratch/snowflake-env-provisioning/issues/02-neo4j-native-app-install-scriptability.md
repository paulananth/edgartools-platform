# Can the Neo4j Graph Analytics Native App be installed on a brand-new Snowflake account without manual UI steps?

Type: research
Status: resolved

## Question

Per CLAUDE.md, graph data lives inside Snowflake via the **Neo4j Graph
Analytics Native App** (Snowflake Marketplace listing), installed into the
same account as gold — `mdm sync-graph`/`mdm verify-graph` and
`infra/snowflake/sql/neo4j_graph_analytics_app_grants.sql` assume it's
already installed. That grants file has only ever been applied against the
existing prod account (`XCPCLKF`), where the Native App was presumably
installed once, by hand, at some earlier point not documented in this repo.

For the one-shot provisioning script's destination to be real, we need to
know: can installing this Native App into a **brand-new** Snowflake account
be done entirely via SQL/CLI (e.g. `CREATE APPLICATION ... FROM
"<listing>"`, or a documented Snowflake CLI / API call), or does Snowflake
require a one-time manual Snowsight UI step per account (accepting
Marketplace terms, consenting to the listing) that cannot be scripted?

Research primary sources: Snowflake's official docs on Native App
Marketplace installation (`CREATE APPLICATION` docs, Marketplace
consumer-side installation docs, any documented Terraform
`snowflake_application`/`snowflake_application_package` resource support),
and specifically whether "Graph Analytics" (the Neo4j-branded native app)
has any installation quirks (compute pool requirements, region
availability, org-level acceptance flags) beyond a generic Native App.

Report: (1) whether SQL-only install is possible and the exact statement
sequence if so, (2) if manual UI acceptance is unavoidable, exactly what
that one-time step is and whether it's per-account or per-organization, (3)
citations to the Snowflake docs pages used.

## Answer

**Bottom line: no, full end-to-end automation from a brand-new Snowflake
organization is not achievable — Snowflake's own docs describe (and give
no SQL/API alternative for) one one-time, per-organization manual
Snowsight step that gates *any* Marketplace install (including this app).
There is no typed Terraform resource for the install itself, though the
provider's generic `snowflake_execute` escape hatch can run the raw SQL
(see §2). Once that one manual step has happened for an org, the actual
app install can be scripted with a real, documented SQL statement.**

### 1. Is there a SQL-only install statement?

Yes. `CREATE APPLICATION` supports installing directly from a Marketplace
listing:

```sql
CREATE APPLICATION <name> FROM LISTING <listing_global_name>
   [ USING RELEASE CHANNEL { QA | ALPHA | DEFAULT } ]
   [ COMMENT = '<string_literal>' ]
   [ [ WITH ] TAG ( <tag_name> = '<tag_value>' [ , ... ] ) ]
   [ BACKGROUND_INSTALL = { TRUE | FALSE } ]
   [ AUTHORIZE_TELEMETRY_EVENT_SHARING = { TRUE | FALSE } ]
   [ WITH FEATURE POLICY = <policy_name> ]
```

Reference: the listing is identified by its **global name**, not its
display name. Required privileges: `CREATE APPLICATION` on the account,
plus `IMPORT SHARE` when installing across accounts.
`BACKGROUND_INSTALL = TRUE` makes the install non-blocking (returns
immediately, poll `DESCRIBE APPLICATION` for completion) — useful for
scripting.
Source: [CREATE APPLICATION | Snowflake Documentation](https://docs.snowflake.com/en/sql-reference/sql/create-application)
(Note: the clause list above was extracted by a page-summarizing fetch, not
read verbatim from the rendered doc — the `FROM LISTING <global_name>`
form, the privilege requirements, and `BACKGROUND_INSTALL` are the
load-bearing, near-certainly-correct parts; treat the exact bracketed
clause ordering as approximate and re-check the live page before hand-typing
it into a script.)

However, Snowflake's own consumer-facing install guides — both the
generic one and the container-app-specific one (Graph Analytics is a
container app, see §4) — document **only** the Snowsight "Get"/"Buy"
button flow and never show `CREATE APPLICATION ... FROM LISTING` as the
supported consumer install path:
- [Install an app from a listing | Snowflake Documentation](https://docs.snowflake.com/en/developer-guide/native-apps/ui-consumer-installing) — entirely Snowsight-UI-described ("Sign in to Snowsight", menu navigation); no SQL-only method mentioned.
- [Install and manage an app with containers | Snowflake Documentation](https://docs.snowflake.com/developer-guide/native-apps/ui-consumer-installing-container) — same: UI-only walkthrough (Get/Buy → name app → grant privileges incl. `CREATE COMPUTE POOL`/`BIND SERVICE ENDPOINT` → Activate → Launch); "makes no mention of SQL-only or non-UI installation methods."

So the SQL primitive exists and is real, but Snowflake does not officially
demonstrate it for a Marketplace *consumer* install in any doc found —
nothing found contradicts it working once the org-level terms gate below
is cleared, it's simply undemonstrated for this exact flow in the primary
docs surveyed.

### 2. Terraform support

**No.** The official provider (`snowflakedb/terraform-provider-snowflake`,
published at
[registry.terraform.io/providers/snowflakedb/snowflake](https://registry.terraform.io/providers/snowflakedb/snowflake))
has no `snowflake_application` or `snowflake_application_package`
resource. Confirmed directly against the provider's tracked docs directory
(`docs/resources/`) via the GitHub API
(`gh api repos/snowflakedb/terraform-provider-snowflake/contents/docs/resources`):
the only "application"-related resource that exists is
[`grant_application_role.md`](https://github.com/snowflakedb/terraform-provider-snowflake/blob/main/docs/resources/grant_application_role.md),
which grants an *already-installed* app's application role to another
role — it does not create/install the app. No `snowflake_application_*`
resource and no open GitHub feature-request issue for one were found in a
search of the repo's issues/PRs (`gh api search/issues`) as of this
research.

**Practical implication for the one-shot script:** there is no typed,
first-class Terraform resource for this, but the provider does ship a
generic escape hatch —
[`snowflake_execute`](https://github.com/snowflakedb/terraform-provider-snowflake/blob/main/docs/resources/execute.md)
("Resource allowing execution of **ANY** SQL statement," explicitly
flagged by the provider's own docs as "dangerous," with no drift
detection and a caller-supplied `revert` statement instead of real
delete semantics). So the install *can* technically live inside a
Terraform root via `snowflake_execute { execute = "CREATE APPLICATION ...
FROM LISTING ..." revert = "DROP APPLICATION ..." }` — but it inherits all
of that resource's caveats (no built-in idempotency check beyond
create/destroy, the provider's own warning against combining it with
typed resources, no verification that a re-`apply` won't error on an
already-installed app unless the script wraps it in `query`/lifecycle
guards itself). Whether to use `snowflake_execute` here vs. a plain
SQL/SnowCLI step run alongside (not inside) Terraform is a design choice
for the implementation ticket, not a scriptability blocker — either path
works; `snowflake_execute` buys single-tool orchestration at the cost of
losing the type/drift safety the rest of this provider gives you.

### 3. Marketplace terms acceptance — scope, role, and whether it's scriptable

This is the actual blocker. Snowflake's Marketplace/Native-App-listing
access is gated by the **Snowflake Provider and Consumer Terms**, and
acceptance of those terms is:

- **Per-organization, one-time.** "The organization administrator only
  needs to accept the Snowflake Provider and Consumer Terms once for your
  organization" — so on a genuinely new org this has never happened and
  must happen before *any* listing (free, paid, or Native App) can be
  installed by *any* means, SQL included.
- **Requires the `ORGADMIN` role** specifically (not `ACCOUNTADMIN` —
  accessing a listing afterward needs `ACCOUNTADMIN`/`CREATE DATABASE` +
  `IMPORT SHARE`, but *accepting the org-level terms* needs `ORGADMIN`).
- **Snowsight UI only, no SQL/API alternative documented.** The exact
  documented path: sign in to Snowsight → **Admin » Terms** → Snowflake
  Marketplace section → **Review** → accept checkbox → **Save**. Until
  this happens, Snowsight itself shows a "Setup incomplete" dialog blocking
  any `Get`.

  Sources:
  - [Use listings as a consumer | Snowflake Documentation](https://docs.snowflake.com/en/collaboration/consumer-becoming) — states the ORGADMIN requirement, the once-per-organization scope, and the exact Snowsight menu path; no SQL alternative mentioned anywhere on the page.
  - [Legal requirements for providers and consumers of listings | Snowflake Documentation](https://docs.snowflake.com/en/collaboration/collaboration-listings-legal) — corroborates "the organization administrator (the user with the ORGADMIN role) ... must agree to the Snowflake Provider and Consumer Terms."
  - [Access and install listings as a consumer | Snowflake Documentation](https://docs.snowflake.com/en/collaboration/consumer-listings-access) — "If your organization administrator has not previously accepted the Provider and Consumer Terms, the Setup incomplete dialog appears," blocking access until it's done at the org level; explicitly does not mention any SQL-based way to do this.

  **Important nuance found:** Snowflake *does* have a SQL-callable
  function, `SYSTEM$ACCEPT_LEGAL_TERMS('<listing_type>', '<listing_id>')`
  (e.g. `CALL SYSTEM$ACCEPT_LEGAL_TERMS('DATA_EXCHANGE_LISTING',
  'GZ1MXZFTF1')`), documented at
  [Manage listings with SQL as a consumer - examples | Snowflake Documentation](https://docs.snowflake.com/collaboration/consumer-listings-progaccess-examples).
  **This is not a substitute** for the org-level Provider and Consumer
  Terms above — it accepts terms for one *specific* listing (used e.g. for
  Data Exchange listings that carry their own extra terms), and the org-level
  gate must already be cleared first. It does not appear applicable to
  clearing the initial org-wide Marketplace enablement gate.

### 4. Graph Analytics (Neo4j-branded) app-specific quirks

- It is a **container app** (built on Snowpark Container Services, not a
  plain warehouse-based Native App) — confirmed via both Snowflake's own
  developer guide and Neo4j's own product docs. Its Marketplace listing
  global name is `GZTDZH40CN` (visible in the `app.snowflake.com/marketplace/listing/GZTDZH40CN`
  link cited from Snowflake's own guide).
  Source: [Integrating Snowflake and Neo4j: Practical Graph Analytics for your Data | Snowflake Developers](https://www.snowflake.com/en/developers/guides/practical-graph-analytics-neo4j-snowflake/)
- Both Snowflake's own guide and Neo4j's vendor docs
  ([The Neo4j Graph Analytics for Snowflake manual](https://neo4j.com/docs/snowflake-graph-analytics/current/),
  its [Getting started](https://neo4j.com/docs/snowflake-graph-analytics/current/getting-started/)
  and [Administration](https://neo4j.com/docs/snowflake-graph-analytics/current/administration/)
  pages — vendor's own official product documentation, not a blog)
  document install as Marketplace-UI-only ("Native App ... installed from
  the Snowflake Marketplace"); neither shows a `CREATE APPLICATION`
  example for this specific listing.
- **Privileges the app itself needs after install:** `CREATE COMPUTE POOL`
  and `CREATE WAREHOUSE`, granted to the app. Documented easiest path is
  Snowsight (Data Products → Apps → Neo4j Graph Analytics → Privileges →
  Grant, then **Activate**, which triggers the app to provision its own
  compute pool) — but these are ordinary account-level grants
  (`GRANT CREATE COMPUTE POOL ON ACCOUNT TO APPLICATION <name>`-shaped),
  so nothing here looks inherently unscriptable via SQL once the app
  object exists; it's just that neither official doc shows the SQL form.
- **Post-install setup requires `ACCOUNTADMIN`** to create a consumer
  role/database role and grant the application's role to it — ordinary SQL
  (`GRANT APPLICATION ROLE ... TO ROLE ...`), fully scriptable.
- **Region/availability restriction (real, and applies because this is a
  container app):** per Snowflake's own Native App Framework limitations
  page, "Apps with containers are only supported on specific AWS, Azure,
  and Google Cloud commercial regions" and are explicitly **not** enabled
  by default in Virtual Private Snowflake, and government-region support
  is narrow ("Only FedRAMP Moderate on `awsuseast1gov` supported" for AWS
  gov; Azure GovCloud limited to US East N. Virginia).
  Source: [Understand limitations in the Snowflake Native App Framework | Snowflake Documentation](https://docs.snowflake.com/developer-guide/native-apps/limitations)
  This is a real constraint for the one-shot script's target-region
  parameter (a brand-new account provisioned into a VPS or unsupported gov
  region would need this app skipped or special-cased) but is not itself a
  scriptability blocker for ordinary AWS/Azure/GCP commercial regions —
  the map's actual trigger account (`AWS_US_WEST_2`, a standard AWS
  commercial region) is not one of the restricted cases documented here.

### Net for the wayfinder map

For the one-shot script: budget one **manual, human-in-the-loop,
one-time-per-organization** step — an `ORGADMIN` accepting the Snowflake
Provider and Consumer Terms via Snowsight (Admin » Terms) — as a hard
precondition before the script can run `CREATE APPLICATION <name> FROM
LISTING '<listing_global_name>'` (verify the actual global name for Graph
Analytics at run time — see caveat below — rather than hardcoding
`GZTDZH40CN`) against a brand-new organization for the first time.

**Scope caveat, stated explicitly because it's load-bearing for an
Nth-environment map:** Snowflake's fetched primary doc
([consumer-becoming](https://docs.snowflake.com/en/collaboration/consumer-becoming))
states in its own words, "The organization administrator only needs to
accept the Snowflake Provider and Consumer Terms once for your
organization" — this repo's earlier ad-hoc web-search synthesis (not a
fetched primary page, weaker evidence) had instead said "once for your
Snowflake account," so the two disagree on scope and the primary-source
wording ("organization") is what's used above. What that page does
**not** explicitly state, and what was **not independently tested**
against a live second-account creation in this research pass, is the
practical consequence this map actually cares about: whether provisioning
a *second new account inside an org that already cleared this step* still
requires a repeat of the Snowsight click. The docs' own phrasing implies
no (it's framed as an organization-wide, not account-wide, one-time
action), so this map should plan for "one manual step, first new org
only" — but treat that specific inference as docs-implied, not empirically
confirmed, until someone actually stands up a second account in an
already-cleared org and checks.

The actual app install and all post-install grant/role wiring, once that
one gate is cleared, is fully SQL-scriptable — no typed Terraform resource
exists for the install itself (§2), but `snowflake_execute` can carry it
inside a Terraform root if the map prefers single-tool orchestration over
a separate SQL/SnowCLI step.

**Also flag before use:** the listing global name `GZTDZH40CN` cited above
for "Graph Analytics" was transcribed by a page-summarizing fetch from a
URL embedded in a Snowflake developer guide, not read directly off a
`SHOW AVAILABLE LISTINGS` result — treat it as unverified until confirmed
live. Prefer having the provisioning script resolve the listing at run
time (`SHOW AVAILABLE LISTINGS` / `DESCRIBE AVAILABLE LISTING`, both
documented at
[Manage listings with SQL as a consumer - examples](https://docs.snowflake.com/collaboration/consumer-listings-progaccess-examples))
rather than hardcoding a global name that could drift or was mistranscribed.
