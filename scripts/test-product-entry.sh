#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

test_root="$(mktemp -d)"
cleanup() {
  rm -rf -- "$test_root"
}
trap cleanup EXIT

config_path="$test_root/vyane.toml"
capture_path="$test_root/args"
fake_vyane="$test_root/vyane"

printf '# synthetic\n' >"$config_path"
cp "$repo_root/bin/vyane-paw-mcp" "$test_root/launcher"

cat >"$fake_vyane" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$@" >"${VYANE_PAW_TEST_CAPTURE:?}"
EOF
chmod 0755 "$fake_vyane" "$test_root/launcher"

VYANE_PAW_CONFIG="$config_path" \
VYANE_PAW_VYANE_BIN="$fake_vyane" \
VYANE_PAW_TEST_CAPTURE="$capture_path" \
  "$test_root/launcher"

mapfile -t args <"$capture_path"
expected=(--config "$config_path" mcp)
if [[ "${args[*]}" != "${expected[*]}" ]]; then
  echo "Launcher forwarded unexpected arguments." >&2
  exit 1
fi

if VYANE_PAW_VYANE_BIN="$fake_vyane" "$test_root/launcher" \
  >"$test_root/missing.out" 2>"$test_root/missing.err"; then
  echo "Launcher accepted a missing VYANE_PAW_CONFIG." >&2
  exit 1
fi
if grep -F "$test_root" "$test_root/missing.err" >/dev/null; then
  echo "Launcher error leaked an absolute path." >&2
  exit 1
fi

if VYANE_PAW_CONFIG="$test_root/not-found.toml" \
  VYANE_PAW_VYANE_BIN="$fake_vyane" \
  "$test_root/launcher" \
  >"$test_root/not-found.out" 2>"$test_root/not-found.err"; then
  echo "Launcher accepted a missing configuration file." >&2
  exit 1
fi
if grep -F "$test_root" "$test_root/not-found.err" >/dev/null; then
  echo "Missing-file error leaked an absolute path." >&2
  exit 1
fi

mkdir "$test_root/bin"
cp "$fake_vyane" "$test_root/bin/vyane"
PATH="$test_root/bin:$PATH" \
VYANE_PAW_CONFIG="$config_path" \
VYANE_PAW_VYANE_BIN="vyane" \
VYANE_PAW_TEST_CAPTURE="$capture_path" \
  "$test_root/launcher"
mapfile -t bare_args <"$capture_path"
if [[ "${bare_args[*]}" != "${expected[*]}" ]]; then
  echo "Bare-name launcher path forwarded unexpected arguments." >&2
  exit 1
fi

echo "Vyane Paw product-entry launcher passed."
