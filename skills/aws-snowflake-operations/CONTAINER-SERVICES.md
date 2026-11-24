# Container services and in-Snowflake storage: probing before a design

Read before designing anything that runs inside Snowflake (a compute pool, a job service, a stage volume, a
Snowflake Postgres instance reached from a service). Each rule below came from a probe; the method is at the end.

## Check these first

- **External access is refused on a trial account** ("External access is not supported for trial accounts"). Creating
  the external access integration fails, and so does any service that needs it. Without one, a service reaches no host
  outside Snowflake: no provider fetch and no Snowflake Postgres. Create a throwaway integration before any design that
  relies on egress; the answer is a compile error, free and immediate.
- **No always-on pool.** A pool exists for a load: auto-suspend at its shortest, a job service that ends with the
  load, nothing running between loads. Price one load window (credits per node-hour of the family, times the hours,
  plus the pool's start time), never 24 hours.
- **A pool takes about two minutes to go from starting to idle**; that is added to every load.
- **The credit rows of a pool reach the account's metering history up to three hours after it is dropped.** Read them
  then; a probe's cost is not visible when it ends.
- **An internal stage mounts as a volume without external access.** Large sequential files move at tens of MB/s;
  small files cost tens of milliseconds each, about twenty times a local disk, so a load that reads many small
  captures reads them from one packed file or copies them to the container's local disk first.
- **An external stage needs a storage integration** (an AWS role trust, a change in the AWS account) and is read by
  Snowflake, not mounted into a container. List the account's integrations and external volumes first; none means the
  test waits for the operator's words and the AWS side.
- **Reaching Snowflake Postgres** needs an ingress policy rule (and private connectivity only on the top edition).
  Never change the hosted instance's policy to test; use a throwaway instance that references the existing policy.

## Probe method

1. Read-only first: edition and region, instance families, pools, integrations, stages.
2. One billable object at a time, each named for the probe and dropped when the test ends, in this order: instance,
   database with image repository, pool, job. Drop them all, then list each kind and confirm none remains.
3. Credentials: the creation of a Postgres instance returns its logins once. Write the answer to a private file
   (mode 600, outside Git), read it from a script that never prints a field, and delete the file with the instance.
   Never print `snow spcs image-repository url` or the registry host: it holds the account locator.
4. Measure what the claim names (round trips, throughput, start time) and say "measured"; say "from the
   documentation" for the rest.
5. The admin login is used only on the operator's explicit words for that probe, recorded with the words and time;
   the audit and logs logins are the default.
