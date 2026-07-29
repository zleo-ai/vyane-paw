#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
runtime_root="${VYANE_PAW_RUNTIME_DIR:-$repo_root/runtime}"
qwenpaw_dir="$runtime_root/qwenpaw-src"
evidence_path="${VYANE_PAW_EVIDENCE_PATH:-$runtime_root/evidence/vp03-product-entry.json}"

"$repo_root/scripts/run-vp02.sh"

uv run \
  --project "$repo_root/compat" \
  --locked \
  python "$repo_root/compat/plugin_contract.py" \
  --qwenpaw-architecture \
  "$qwenpaw_dir/src/qwenpaw/plugins/architecture.py" \
  --upstreams-lock "$repo_root/upstreams.lock.json" \
  --evidence "$evidence_path"

"$repo_root/scripts/test-product-entry.sh"

uv run \
  --project "$repo_root/compat" \
  --locked \
  check-jsonschema \
  --schemafile "$repo_root/schemas/evidence.schema.json" \
  "$evidence_path"

jq -e \
  '.scenario == "product_entry"
   and .result == "passed"
   and .metrics.validated_product_modes == 4
   and .metrics.fixed_private_paths == 0' \
  "$evidence_path" \
  >/dev/null

echo "VP-03 product-entry smoke passed."
