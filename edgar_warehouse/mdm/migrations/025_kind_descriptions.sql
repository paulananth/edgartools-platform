-- Complete destination vocabulary descriptions without changing migration 024.
COMMENT ON COLUMN mdm.master_kind.kind IS
    'Configured master kind. The owner installs vocabulary; runtime may read it but cannot change it.';
COMMENT ON COLUMN mdm.master_kind.enabled IS
    'Whether the installed configuration permits new identities of this kind. Disabling retains existing identities and read views.';
COMMENT ON FUNCTION mdm.require_configured_kind() IS
    'Destination guard for new or changed identity kinds. Locks the configured vocabulary row and refuses a kind that is not enabled.';
