"""Platform adapters for the access audit.

An adapter is a module with `NAME`, `configured(env) -> bool`, `collect(env, as_admin) -> dict` (read-only evidence: counts
and names, never a secret) and `controls(evidence) -> list[dict]`. Each control carries an `objective` from
`audit_platforms.base.OBJECTIVES`; an objective an adapter does not return is reported as a gap, never as a pass.
"""
