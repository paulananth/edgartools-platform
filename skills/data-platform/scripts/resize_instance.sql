-- Apply an explicitly approved compute-family change using Snow CLI Jinja.
-- Required -D variables: instance_name and compute_family, reviewed literals.
-- Accept instance_name only if it matches ^[A-Za-z_][A-Za-z0-9_]*$.
-- Accept compute_family only from the documented supported family list.
-- Jinja is textual substitution: never pass unreviewed or data-derived input.
-- Use a role with MODIFY/OWNERSHIP, an explicit connection and JINJA templating.
-- Approval covers increased compute cost and failover as soon as ready.
-- This requests maintenance; verify the resulting family and READY afterward.
-- Do not print DESCRIBE results: they may contain access_roles credentials.
ALTER POSTGRES INSTANCE {{ instance_name }}
  SET COMPUTE_FAMILY = '{{ compute_family }}'
  APPLY IMMEDIATELY;
