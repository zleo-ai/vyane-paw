#!/usr/bin/env bash
# VP-12 cancellation-propagation adoption canary.
#
# Advisory by design: this script passes while upstream adoption of the MCP
# Python SDK dispatcher cancellation behavior remains blocked, and fails
# loudly once a current agentscope release allows mcp 2.x — the signal to
# re-run the full QwenPaw-plus-SDK-v2 spike from ADR-0003. It never rewrites
# the stable compatibility claim by itself.
set -euo pipefail

repo_root="${VYANE_PAW_REPO_ROOT:-$(git rev-parse --show-toplevel)}"
runtime_root="${VYANE_PAW_RUNTIME_DIR:-$repo_root/runtime}"
evidence_path="${VYANE_PAW_EVIDENCE_PATH:-$runtime_root/evidence/vp12-cancellation-adoption.json}"

# httpx honors ALL_PROXY; this deployment exports a socks proxy without the
# socksio extra, while the HTTP(S) proxy variables work without it.
env -u ALL_PROXY -u all_proxy \
  uv run \
  --project "$repo_root/compat" \
  --locked \
  python "$repo_root/compat/cancellation_adoption_probe.py" \
  --app-lock "$repo_root/compat/qwenpaw-app/uv.lock" \
  --upstreams-lock "$repo_root/upstreams.lock.json" \
  --evidence "$evidence_path"

uv run \
  --project "$repo_root/compat" \
  --locked \
  check-jsonschema \
  --schemafile "$repo_root/schemas/evidence.schema.json" \
  "$evidence_path"

if ! jq -e \
  '.scenario == "cancellation"
   and .result == "passed"
   and .metrics.cancellation_probe_completed == 1
   and .metrics.pinned_chain_adopts_fix == 0
   and .metrics.agentscope_allows_mcp2 == 0' \
  "$evidence_path" \
  >/dev/null; then
  echo "VP-12 adoption canary fired: upstream may now allow MCP SDK v2." >&2
  echo "Re-run the ADR-0003 QwenPaw-plus-SDK-v2 spike before changing any claim." >&2
  exit 1
fi

echo "VP-12 cancellation-adoption probe passed: upstream adoption still blocked."
