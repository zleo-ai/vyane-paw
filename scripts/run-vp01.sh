#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
runtime_root="${VYANE_PAW_RUNTIME_DIR:-$repo_root/runtime}"
qwenpaw_dir="$runtime_root/qwenpaw-src"
compatibility_lane="${VYANE_PAW_COMPATIBILITY_LANE:-stable}"

qwenpaw_revision="$(
  jq -r '.upstreams.qwenpaw.revision' "$repo_root/upstreams.lock.json"
)"
qwenpaw_repository="$(
  jq -r '.upstreams.qwenpaw.repository' "$repo_root/upstreams.lock.json"
)"
vyane_repository="$(
  jq -r '.upstreams.vyane_rs.repository' "$repo_root/upstreams.lock.json"
)"
stable_vyane_revision="$(
  jq -r '.upstreams.vyane_rs.revision' "$repo_root/upstreams.lock.json"
)"
declared_rmcp_version="$(
  jq -r '.upstreams.rmcp.version' "$repo_root/upstreams.lock.json"
)"

case "$compatibility_lane" in
  stable)
    vyane_revision="$stable_vyane_revision"
    vyane_dir="$runtime_root/vyane-rs-src"
    default_evidence_path="$runtime_root/evidence/vp01-stable.json"
    ;;
  candidate)
    vyane_revision="$(
      git ls-remote "$vyane_repository" refs/heads/main |
        awk 'NR == 1 { print $1 }'
    )"
    if [[ ! "$vyane_revision" =~ ^[0-9a-f]{40}$ ]]; then
      echo "unable to resolve the vyane-rs candidate main revision" >&2
      exit 1
    fi
    vyane_dir="$runtime_root/vyane-rs-candidate-src"
    default_evidence_path="$runtime_root/evidence/vp01-candidate.json"
    ;;
  *)
    echo "unsupported compatibility lane: $compatibility_lane" >&2
    exit 1
    ;;
esac
evidence_path="${VYANE_PAW_EVIDENCE_PATH:-$default_evidence_path}"

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
prepare_upstream \
  "$qwenpaw_repository" \
  "$qwenpaw_revision" \
  "$qwenpaw_dir"
prepare_upstream \
  "$vyane_repository" \
  "$vyane_revision" \
  "$vyane_dir"

uv run \
  --project "$repo_root/compat" \
  --locked \
  python "$repo_root/compat/plugin_contract.py" \
  --qwenpaw-architecture \
  "$qwenpaw_dir/src/qwenpaw/plugins/architecture.py"

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
  python "$repo_root/compat/smoke.py" \
  --qwenpaw-client \
  "$qwenpaw_dir/src/qwenpaw/drivers/handlers/mcp_stateful_client.py" \
  --vyane-bin "$vyane_dir/target/debug/vyane" \
  --compatibility-lane "$compatibility_lane" \
  --vyane-revision "$vyane_revision" \
  --rmcp-version "$locked_rmcp_version" \
  --upstreams-lock "$repo_root/upstreams.lock.json" \
  --evidence "$evidence_path"

jq -e \
  --arg lane "$compatibility_lane" \
  --arg revision "$vyane_revision" \
  '.result == "passed"
   and .metrics.discovered_tools == 9
   and .upstream_revisions.compatibility_lane == $lane
   and .upstream_revisions.vyane_rs == $revision' \
  "$evidence_path" \
  >/dev/null

echo "VP-01 $compatibility_lane compatibility smoke passed at $vyane_revision."
