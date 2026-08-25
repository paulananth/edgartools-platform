#!/usr/bin/env bash
# Ticket 32 item 3 (extended by Ticket 21 for the submissions family): open
# and activate the first Source Family Registry version, covering every
# family a fresh environment needs -- the one committed, re-runnable
# bootstrap path this system needs before drive-filing-discovery-for-date/
# capture-filing-artifact/drive-submissions-discovery can run at all. All
# three commands hard-require an active registry version covering their own
# family (NoActiveRegistryVersion / UnsupportedAcquisitionMode /
# UnsupportedDiscoveryPolicy otherwise) -- before this script existed, the
# only place this sequence was written down was duplicated inline in test
# fixtures (`_activate_filing_artifact_registry` in
# test_capture_filing_artifact_command.py and
# test_drive_filing_discovery_command.py, `_activate_submissions_registry`
# in test_drive_submissions_discovery_command.py), which is not a
# deliverable. Both families are declared in ONE draft/activate here, not
# two separate scripts -- Ticket 20's model is one active version covering
# every currently-in-scope family, and this script's own idempotency guard
# below (checking whether ANY version is already active) would make a
# second script for a second family silently no-op instead of adding its
# coverage.
#
# Idempotent once a version has actually activated: does nothing if a
# registry version is already active (checked via `mdm registry-status`'s
# exit code) -- safe to call on every install/deploy run, not just a
# first-time one. Not perfectly idempotent mid-run: `source_registry_version`
# has no uniqueness constraint on 'draft' rows, so a crash between
# registry-open-draft and registry-activate leaves an orphaned, never-
# activated draft that a re-run does not clean up or reuse -- it just opens
# another draft and activates that one instead. Harmless (an unactivated
# draft has no effect on get_active_registry()/build_active_source_family_
# registry(), and this script only runs during install/bootstrap, not on a
# hot path), but real: don't read "idempotent" here as "leaves zero debris."
#
# Usage:
#   bash infra/scripts/bootstrap-source-family-registry.sh
#
# Requires the same environment `edgar-warehouse mdm` subcommands already
# require (MDM_DATABASE_URL, etc.) -- this script does not set them itself,
# matching every other infra/scripts/*.sh that wraps `edgar-warehouse`.

set -euo pipefail

EDGAR_WAREHOUSE=(uv run --extra s3 --extra mdm-runtime edgar-warehouse)

if "${EDGAR_WAREHOUSE[@]}" mdm registry-status >/dev/null 2>&1; then
  echo "bootstrap-source-family-registry: a Source Family Registry version is already active -- nothing to do."
  exit 0
fi

echo "bootstrap-source-family-registry: no active registry version found -- opening and activating the first one for filing_artifact and submissions."

# No prior history to catch up on for a brand-new environment: today is the
# chosen baseline (catchup_required_through_date), and this script itself
# is the operator asserting that baseline is caught up (registry-record-
# catchup below) -- not a real discovery-drive run, since none can run yet
# without an active registry (the chicken-and-egg this bootstrap exists to
# break). Every future date is caught up normally, by
# drive-filing-discovery-for-date's own real record_catchup_progress call
# (Ticket 20/29's wiring) as it completes each business date going forward.
today="$(date -u +%F)"

# AWS teardown 5-whys (CLAUDE.md): BSD/macOS mktemp only substitutes
# *trailing* X's, so the .json suffix has to be appended after mktemp runs,
# not baked into its own template. That also means mktemp's own file (the
# pre-.json path) is a second, real temp file on disk, not just a name --
# clean up both, not only the renamed one.
coverage_file_base="$(mktemp -t filing-artifact-registry-bootstrap-XXXXXX)"
coverage_file="${coverage_file_base}.json"
trap 'rm -f "${coverage_file_base}" "${coverage_file}"' EXIT

cat > "${coverage_file}" <<JSON
[
  {
    "source_family": "filing_artifact",
    "coverage_action": "add",
    "in_scope_forms": ["3", "3/A", "4", "4/A", "5", "5/A"],
    "acquisition_mode": "on_demand_fetch",
    "completeness_policy": "non_empty_payload",
    "discovery_policy": "daily_index_driven",
    "required_producers": ["sec_raw_object"],
    "coverage_start_date": "${today}",
    "catchup_required_through_date": "${today}"
  },
  {
    "source_family": "submissions",
    "coverage_action": "add",
    "acquisition_mode": "on_demand_fetch",
    "completeness_policy": "valid_json_object",
    "discovery_policy": "cik_universe_driven",
    "required_producers": ["sec_company", "sec_company_filing"],
    "coverage_start_date": "${today}",
    "catchup_required_through_date": "${today}"
  }
]
JSON

draft_output="$("${EDGAR_WAREHOUSE[@]}" mdm registry-open-draft \
  --coverage "${coverage_file}" \
  --operator-authorization-reference "bootstrap-source-family-registry.sh")"
echo "${draft_output}"

version_id="$(printf '%s' "${draft_output}" | python3 -c 'import json, sys
print(json.load(sys.stdin)["version_id"])')"

"${EDGAR_WAREHOUSE[@]}" mdm registry-record-catchup filing_artifact --through-date "${today}"
"${EDGAR_WAREHOUSE[@]}" mdm registry-record-catchup submissions --through-date "${today}"

"${EDGAR_WAREHOUSE[@]}" mdm registry-activate "${version_id}"

echo "bootstrap-source-family-registry: activated version_id=${version_id} for filing_artifact and submissions, caught up through ${today}."
