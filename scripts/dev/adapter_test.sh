#!/usr/bin/env bash
# Storage-adapter tests on each engine: one deadline, one exit code, no leftover containers.
#
# Usage: bash scripts/dev/adapter_test.sh <pytest paths or node ids>
# ADAPTER_ENGINES (default "postgresql mysql") and ADAPTER_MINUTES (default 4, for the whole run).
# TEST_PYTHON (default .venv/bin/python) names an interpreter that has the project's packages.
# Exit 0 only when every engine passed. Exit 1: a test failed. Exit 2: the deadline passed.
set -uo pipefail

python="${TEST_PYTHON:-.venv/bin/python}"
existing=$(docker ps -aq --filter name=skill-adapter-proof | sort)
deadline=$(( $(date +%s) + ${ADAPTER_MINUTES:-4} * 60 ))
status=0

clean() {
  for container in $(comm -13 <(printf '%s\n' "$existing") <(docker ps -aq --filter name=skill-adapter-proof | sort)); do
    docker rm -f "$container" >/dev/null
  done
}
trap clean EXIT

for engine in ${ADAPTER_ENGINES:-postgresql mysql}; do
  PYTHONPATH=. CI=true SKILL_ADAPTER_TEST_ENGINE="$engine" "$python" -m pytest -q -p no:cacheprovider "$@" &
  run=$!
  while kill -0 "$run" 2>/dev/null; do
    if (( $(date +%s) >= deadline )); then
      pkill -P "$run"; kill "$run"; wait "$run" 2>/dev/null
      echo "$engine: deadline passed"; exit 2
    fi
    sleep 1
  done
  wait "$run" || { echo "$engine: FAILED"; status=1; }
done
exit "$status"
