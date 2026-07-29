#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
runtime_root="${VYANE_PAW_RUNTIME_DIR:-$repo_root/runtime/vp06-container}"
image="vyane-paw-candidate:rust-1.97-uv-0.11.28"
proxy_env_args=()

for name in HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy; do
  value="${!name:-}"
  if [[ -n "$value" ]]; then
    if [[ "$value" == *"@"* ]]; then
      echo "credential-bearing proxy URLs are not allowed in candidate CI" >&2
      exit 1
    fi
    proxy_env_args+=(--env "$name")
  fi
done

mkdir -p \
  "$runtime_root/home" \
  "$runtime_root/cargo-home" \
  "$runtime_root/tmp" \
  "$runtime_root/uv-cache" \
  "$runtime_root/uv-python"
runtime_root="$(realpath "$runtime_root")"
source_root="$runtime_root/source-$$"
mkdir -p "$source_root"
git -C "$repo_root" archive --format=tar HEAD |
  tar -xf - -C "$source_root"

docker build \
  --file "$repo_root/compat/candidate.Dockerfile" \
  --tag "$image" \
  "$repo_root/compat"

docker run --rm \
  --read-only \
  --cap-drop ALL \
  --security-opt no-new-privileges \
  --pids-limit 1024 \
  --user "$(id -u):$(id -g)" \
  --tmpfs /tmp:rw,nosuid,nodev,noexec,size=256m \
  --mount "type=bind,src=$source_root,dst=/workspace,readonly" \
  --mount "type=bind,src=$runtime_root,dst=/runtime" \
  --env HOME=/runtime/home \
  --env CARGO_HOME=/runtime/cargo-home \
  --env RUSTUP_HOME=/usr/local/rustup \
  --env TMPDIR=/runtime/tmp \
  --env UV_CACHE_DIR=/runtime/uv-cache \
  --env UV_PROJECT_ENVIRONMENT=/runtime/compat-venv \
  --env UV_PYTHON_INSTALL_DIR=/runtime/uv-python \
  --env VYANE_PAW_RUNTIME_DIR=/runtime \
  --env VYANE_PAW_REPO_ROOT=/workspace \
  "${proxy_env_args[@]}" \
  --workdir /workspace \
  "$image" \
  bash -c \
  './scripts/run-vp06.sh'
