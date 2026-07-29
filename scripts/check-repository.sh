#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

bash -n scripts/*.sh

for file in upstreams.lock.json schemas/*.json config/examples/*.json evidence/*.json; do
  jq empty "$file"
done

uv run --project compat --locked ruff check compat/smoke.py
uv run --project compat --locked ruff format --check compat/smoke.py
uv run --project compat --locked check-jsonschema \
  --schemafile schemas/evidence.schema.json \
  evidence/*.json
uv run --project compat --locked check-jsonschema \
  --schemafile schemas/policy.schema.json \
  schemas/examples/*.policy.json

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
