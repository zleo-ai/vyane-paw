#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

bash -n bin/* scripts/*.sh

for file in upstreams.lock.json schemas/*.json config/examples/*.json evidence/*.json; do
  jq empty "$file"
done

uv run --project compat --locked ruff check compat/*.py qwenpaw-plugin/*.py
uv run --project compat --locked ruff format --check \
  compat/*.py qwenpaw-plugin/*.py
uv run --project compat --locked python compat/plugin_contract.py
./scripts/test-product-entry.sh
uv run --project compat --locked check-jsonschema \
  --schemafile schemas/evidence.schema.json \
  evidence/*.json
uv run --project compat --locked check-jsonschema \
  --schemafile schemas/evidence.schema.json \
  schemas/examples/*.evidence.json
uv run --project compat --locked check-jsonschema \
  --schemafile schemas/policy.schema.json \
  schemas/examples/*.policy.json
uv run --project compat --locked check-jsonschema \
  --schemafile schemas/operation-result.schema.json \
  schemas/examples/*.result.json

invalid_publishable="$(mktemp)"
cleanup() {
  rm -f -- "$invalid_publishable"
}
trap cleanup EXIT
jq '.sanitization_state = "publishable" | del(.publication_review)' \
  evidence/vp03-product-entry.json >"$invalid_publishable"
if uv run --project compat --locked check-jsonschema \
  --schemafile schemas/evidence.schema.json \
  "$invalid_publishable" >/dev/null 2>&1; then
  echo "Evidence became publishable without human review." >&2
  exit 1
fi

if rg -n \
  --glob '*.py' \
  --glob '*.sh' \
  --glob '!check-repository.sh' \
  'sanitization_state.*publishable' \
  compat qwenpaw-plugin scripts; then
  echo "A generator can mark evidence publishable." >&2
  exit 1
fi

forbidden_tracked="$(
  git ls-files |
    grep -Ei '(^|/)(private|internal|source-materials|raw)(/|$)|\.(docx?|xlsx?|pptx?|p12|pfx|pem|key|sqlite|db)$' ||
    true
)"

if [[ -n "$forbidden_tracked" ]]; then
  printf 'Forbidden tracked files:\n%s\n' "$forbidden_tracked" >&2
  exit 1
fi

if git grep -InE '(BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY|gh[pousr]_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,})' -- .; then
  echo "Potential secret-like content found." >&2
  exit 1
fi

echo "Repository checks passed."
