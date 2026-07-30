#!/usr/bin/env bash
set -euo pipefail

repo_root="${VYANE_PAW_REPO_ROOT:-$(git rev-parse --show-toplevel)}"
runtime_root="${VYANE_PAW_RUNTIME_DIR:-$repo_root/runtime}"

qwenpaw_revision="$(
  jq -r '.upstreams.qwenpaw.revision' "$repo_root/upstreams.lock.json"
)"
qwenpaw_repository="$(
  jq -r '.upstreams.qwenpaw.repository' "$repo_root/upstreams.lock.json"
)"
vyane_repository="$(
  jq -r '.upstreams.vyane_rs.repository' "$repo_root/upstreams.lock.json"
)"
vyane_revision="$(
  jq -r '.upstreams.vyane_rs.revision' "$repo_root/upstreams.lock.json"
)"
declared_rmcp_version="$(
  jq -r '.upstreams.rmcp.version' "$repo_root/upstreams.lock.json"
)"

qwenpaw_dir="$runtime_root/qwenpaw-stable-src"
vyane_dir="$runtime_root/vyane-rs-stable-src"
evidence_path="${VYANE_PAW_EVIDENCE_PATH:-$runtime_root/evidence/vp09-capabilities.json}"

prepare_upstream() {
  local repository="$1"
  local revision="$2"
  local destination="$3"

  if [[ -e "$destination" && ! -d "$destination/.git" ]]; then
    echo "upstream destination exists but is not a git checkout: $destination" >&2
    echo "remove or relocate it explicitly before retrying" >&2
    exit 1
  fi

  if [[ ! -e "$destination" ]]; then
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
prepare_upstream "$qwenpaw_repository" "$qwenpaw_revision" "$qwenpaw_dir"
prepare_upstream "$vyane_repository" "$vyane_revision" "$vyane_dir"

cargo build \
  --locked \
  --manifest-path "$vyane_dir/Cargo.toml" \
  --package vyane-cli \
  --bin vyane

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

if [[ "$locked_rmcp_version" != "$declared_rmcp_version" ]]; then
  echo "rmcp version mismatch: upstream lock declares $declared_rmcp_version" >&2
  echo "but pinned vyane-rs Cargo.lock resolves $locked_rmcp_version" >&2
  exit 1
fi

uv run \
  --project "$repo_root/compat" \
  --locked \
  python "$repo_root/compat/capability_probe.py" \
  --self-test

uv run \
  --project "$repo_root/compat" \
  --locked \
  python "$repo_root/compat/capability_probe.py" \
  --qwenpaw-client \
  "$qwenpaw_dir/src/qwenpaw/drivers/handlers/mcp_stateful_client.py" \
  --vyane-bin "$vyane_dir/target/debug/vyane" \
  --compatibility-lane stable \
  --vyane-revision "$vyane_revision" \
  --rmcp-version "$locked_rmcp_version" \
  --upstreams-lock "$repo_root/upstreams.lock.json" \
  --evidence "$evidence_path"

uv run \
  --project "$repo_root/compat" \
  --locked \
  check-jsonschema \
  --schemafile "$repo_root/schemas/evidence.schema.json" \
  "$evidence_path"

jq -e \
  --arg revision "$vyane_revision" \
  '.scenario == "capability_probe"
   and .result == "passed"
   and .metrics.qwenpaw_client_parity == 1
   and .metrics.discover_probe_completed == 1
   and .metrics.product_claimed_extensions == 0
   and .metrics.server_process_reaped == 1
   and (.capabilities.product_claimed | length) == 0
   and .upstream_revisions.compatibility_lane == "stable"
   and .upstream_revisions.vyane_rs == $revision' \
  "$evidence_path" \
  >/dev/null

if ! diff -u \
  <(jq -S 'del(.started_at, .duration_ms)' "$repo_root/evidence/vp09-capabilities.json") \
  <(jq -S 'del(.started_at, .duration_ms)' "$evidence_path"); then
  echo "tracked VP-09 evidence drifted from the current generator" >&2
  exit 1
fi

echo "VP-09 capability-negotiation probe passed at $vyane_revision."
