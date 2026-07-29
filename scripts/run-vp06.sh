#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
runtime_root="${VYANE_PAW_RUNTIME_DIR:-$repo_root/runtime}"
evidence_path="$runtime_root/evidence/vp01-candidate.json"

VYANE_PAW_COMPATIBILITY_LANE=candidate \
VYANE_PAW_EVIDENCE_PATH="$evidence_path" \
  "$repo_root/scripts/run-vp01.sh"

jq -e \
  '.result == "passed"
   and .upstream_revisions.compatibility_lane == "candidate"
   and (.upstream_revisions.vyane_rs | test("^[0-9a-f]{40}$"))
   and .metrics.discovered_tools == 9
   and .metrics.server_process_reaped == 1' \
  "$evidence_path" \
  >/dev/null

echo "VP-06 moving-candidate compatibility canary passed."
