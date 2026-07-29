#!/usr/bin/env bash
set -euo pipefail

repo_root="${VYANE_PAW_REPO_ROOT:-$(git rev-parse --show-toplevel)}"
runtime_root="${VYANE_PAW_RUNTIME_DIR:-$repo_root/runtime}"
vyane_dir="$runtime_root/vyane-rs-stable-src"
app_venv="${VYANE_PAW_QWENPAW_VENV:-$runtime_root/qwenpaw-app-venv}"
app_project="$repo_root/compat/qwenpaw-app"
app_python="$app_venv/bin/python"
app_runtime="$runtime_root/vp07-qwenpaw-application-$$"
evidence_path="$runtime_root/evidence/vp07-qwenpaw-application.json"

"$repo_root/scripts/run-vp01.sh"

qwenpaw_revision="$(
  jq -r '.upstreams.qwenpaw.revision' "$repo_root/upstreams.lock.json"
)"
if ! grep -Fq -- "$qwenpaw_revision" "$app_project/uv.lock"; then
  echo "Locked QwenPaw application revision drifted." >&2
  exit 1
fi

PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 \
  UV_PROJECT_ENVIRONMENT="$app_venv" \
  uv sync \
    --project "$app_project" \
    --locked \
    --python 3.13

rmcp_version="$(
  jq -r '.upstreams.rmcp.version' "$repo_root/upstreams.lock.json"
)"

"$app_python" "$repo_root/compat/qwenpaw_app.py" \
  --plugin-dir "$repo_root/qwenpaw-plugin" \
  --launcher "$repo_root/bin/vyane-paw-mcp" \
  --vyane-bin "$vyane_dir/target/debug/vyane" \
  --runtime-root "$app_runtime" \
  --upstreams-lock "$repo_root/upstreams.lock.json" \
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
   and .metrics.mcp_process_reaped == 1
   and .metrics.model_visible_tools == 1
   and .metrics.normalized_results == 1
   and .metrics.operator_interventions == 0' \
  "$evidence_path" \
  >/dev/null

echo "VP-07 headless QwenPaw application integration passed."
