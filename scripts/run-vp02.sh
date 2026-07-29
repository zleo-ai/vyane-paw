#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
runtime_root="${VYANE_PAW_RUNTIME_DIR:-$repo_root/runtime}"
qwenpaw_dir="$runtime_root/qwenpaw-src"
vyane_dir="$runtime_root/vyane-rs-src"
evidence_dir="${VYANE_PAW_EVIDENCE_DIR:-$runtime_root/evidence/vp02}"

"$repo_root/scripts/run-vp01.sh"

locked_rmcp_version="$(
  cargo metadata \
    --locked \
    --manifest-path "$vyane_dir/Cargo.toml" \
    --format-version 1 |
    jq -er '
      [.packages[] | select(.name == "rmcp") | .version]
      | unique
      | if length == 1 then .[0]
        else error("expected exactly one locked rmcp version")
        end
    '
)"

uv run \
  --project "$repo_root/compat" \
  --locked \
  python "$repo_root/compat/demo_flows.py" \
  --qwenpaw-client \
  "$qwenpaw_dir/src/qwenpaw/drivers/handlers/mcp_stateful_client.py" \
  --vyane-bin "$vyane_dir/target/debug/vyane" \
  --rmcp-version "$locked_rmcp_version" \
  --upstreams-lock "$repo_root/upstreams.lock.json" \
  --evidence-dir "$evidence_dir"

uv run \
  --project "$repo_root/compat" \
  --locked \
  check-jsonschema \
  --schemafile "$repo_root/schemas/evidence.schema.json" \
  "$evidence_dir"/*.json

for scenario in route failover broadcast; do
  jq -e \
    --arg scenario "$scenario" \
    '.scenario == $scenario and .result == "passed"' \
    "$evidence_dir/vp02-$scenario.json" \
    >/dev/null
done

echo "VP-02 demo-flow smoke passed."
