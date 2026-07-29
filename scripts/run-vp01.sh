#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
runtime_root="${VYANE_PAW_RUNTIME_DIR:-$repo_root/runtime}"
qwenpaw_dir="$runtime_root/qwenpaw-src"
vyane_dir="$runtime_root/vyane-rs-src"
evidence_path="${VYANE_PAW_EVIDENCE_PATH:-$runtime_root/evidence/vp01.json}"

qwenpaw_revision="$(
  jq -r '.upstreams.qwenpaw.revision' "$repo_root/upstreams.lock.json"
)"
vyane_revision="$(
  jq -r '.upstreams.vyane_rs.revision' "$repo_root/upstreams.lock.json"
)"

prepare_upstream() {
  local repository="$1"
  local revision="$2"
  local destination="$3"

  if [[ ! -d "$destination/.git" ]]; then
    git clone --filter=blob:none "$repository" "$destination"
  fi

  git -C "$destination" fetch --quiet origin "$revision"
  git -C "$destination" checkout --quiet --detach "$revision"

  if [[ "$(git -C "$destination" rev-parse HEAD)" != "$revision" ]]; then
    echo "upstream revision mismatch: $destination" >&2
    exit 1
  fi

  if [[ -n "$(git -C "$destination" status --porcelain)" ]]; then
    echo "upstream checkout is dirty: $destination" >&2
    exit 1
  fi
}

mkdir -p "$runtime_root"
prepare_upstream \
  "https://github.com/agentscope-ai/QwenPaw.git" \
  "$qwenpaw_revision" \
  "$qwenpaw_dir"
prepare_upstream \
  "https://github.com/zleo-ai/vyane-rs.git" \
  "$vyane_revision" \
  "$vyane_dir"

cargo build \
  --locked \
  --manifest-path "$vyane_dir/Cargo.toml" \
  --package vyane-cli \
  --bin vyane

uv run \
  --project "$repo_root/compat" \
  --locked \
  python "$repo_root/compat/smoke.py" \
  --qwenpaw-client \
  "$qwenpaw_dir/src/qwenpaw/drivers/handlers/mcp_stateful_client.py" \
  --vyane-bin "$vyane_dir/target/debug/vyane" \
  --upstreams-lock "$repo_root/upstreams.lock.json" \
  --evidence "$evidence_path"

jq -e \
  '.result == "passed" and .metrics.discovered_tools == 9' \
  "$evidence_path" \
  >/dev/null

echo "VP-01 compatibility smoke passed."
