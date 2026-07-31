#!/usr/bin/env bash
set -euo pipefail

repo_root="${VYANE_PAW_REPO_ROOT:-$(git rev-parse --show-toplevel)}"
runtime_root="${VYANE_PAW_RUNTIME_DIR:-$repo_root/runtime}"
compatibility_lane="${VYANE_PAW_COMPATIBILITY_LANE:-stable}"
app_venv="${VYANE_PAW_QWENPAW_VENV:-$runtime_root/qwenpaw-app-venv}"
app_project="$repo_root/compat/qwenpaw-app"
app_python="$app_venv/bin/python"
app_runtime="$runtime_root/vp08-$compatibility_lane-durable-workflow-$$"
evidence_path="$runtime_root/evidence/vp08-$compatibility_lane-durable-workflow.json"

"$repo_root/scripts/run-vp01.sh"

case "$compatibility_lane" in
  stable)
    vyane_dir="$runtime_root/vyane-rs-stable-src"
    vyane_revision="$(
      jq -r '.upstreams.vyane_rs.revision' "$repo_root/upstreams.lock.json"
    )"
    ;;
  candidate)
    vyane_dir="$runtime_root/vyane-rs-candidate-src"
    vyane_revision="$(git -C "$vyane_dir" rev-parse HEAD)"
    ;;
  *)
    echo "unsupported compatibility lane: $compatibility_lane" >&2
    exit 1
    ;;
esac

qwenpaw_revision="$(
  jq -r '.upstreams.qwenpaw.revision' "$repo_root/upstreams.lock.json"
)"
if ! grep -Fq -- "$qwenpaw_revision" "$app_project/uv.lock"; then
  echo "Locked QwenPaw application revision drifted." >&2
  exit 1
fi

env \
  -u PIP_EXTRA_INDEX_URL \
  -u PIP_INDEX_URL \
  -u UV_EXTRA_INDEX_URL \
  -u UV_INDEX \
  PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 \
  UV_DEFAULT_INDEX=https://pypi.org/simple \
  UV_NO_CONFIG=1 \
  UV_PROJECT_ENVIRONMENT="$app_venv" \
  uv sync \
    --project "$app_project" \
    --locked \
    --python 3.13

rmcp_version="$(
  jq -r '.upstreams.rmcp.version' "$repo_root/upstreams.lock.json"
)"

"$app_python" "$repo_root/compat/qwenpaw_durable.py" \
  --plugin-dir "$repo_root/qwenpaw-plugin" \
  --launcher "$repo_root/bin/vyane-paw-mcp" \
  --vyane-bin "$vyane_dir/target/debug/vyane" \
  --runtime-root "$app_runtime" \
  --upstreams-lock "$repo_root/upstreams.lock.json" \
  --vyane-revision "$vyane_revision" \
  --rmcp-version "$rmcp_version" \
  --evidence "$evidence_path"

uv run \
  --project "$repo_root/compat" \
  --locked \
  check-jsonschema \
  --schemafile "$repo_root/schemas/evidence.schema.json" \
  "$evidence_path"

jq -e \
  '.result == "passed"
   and .metrics.app_exit_code == 0
   and .metrics.app_process_reaped == 1
   and .metrics.daemon_process_reaped == 1
   and .metrics.mcp_process_reaped == 1
   and .metrics.provider_requests >= 1
   and .metrics.repeated_cancel_requests >= 2
   and .metrics.task_log_leaks == 0
   and .metrics.terminal_cancelled == 1
   and .metrics.terminal_succeeded_with_output == 1
   and .metrics.workflow_submitted >= 2' \
  "$evidence_path" \
  >/dev/null

echo "VP-08 durable workflow integration passed."
