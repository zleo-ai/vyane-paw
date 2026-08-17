#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

bash -n bin/* scripts/*.sh
uv lock --check --project compat/qwenpaw-app

uv run --project compat --locked \
  python scripts/check_workflow_trust_boundary.py --self-test
uv run --project compat --locked \
  python scripts/check_workflow_trust_boundary.py

for file in upstreams.lock.json schemas/*.json config/examples/*.json evidence/*.json; do
  jq empty "$file"
done

uv run --project compat --locked ruff check \
  compat/*.py qwenpaw-plugin/*.py scripts/check_workflow_trust_boundary.py
uv run --project compat --locked ruff format --check \
  compat/*.py qwenpaw-plugin/*.py scripts/check_workflow_trust_boundary.py
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
invalid_publishable_log="$(mktemp)"
cleanup() {
  rm -f -- "$invalid_publishable" "$invalid_publishable_log"
}
trap cleanup EXIT
jq '.sanitization_state = "publishable" | del(.publication_review)' \
  evidence/vp03-product-entry.json >"$invalid_publishable"
set +e
uv run --project compat --locked check-jsonschema \
  --schemafile schemas/evidence.schema.json \
  "$invalid_publishable" >"$invalid_publishable_log" 2>&1
schema_status=$?
set -e
case "$schema_status" in
  0)
    echo "Evidence became publishable without human review." >&2
    exit 1
    ;;
  1)
    ;;
  *)
    cat "$invalid_publishable_log" >&2
    echo "Negative evidence-schema check did not execute reliably." >&2
    exit 1
    ;;
esac

set +e
git grep --untracked -n -E \
  'sanitization_state.*publishable' \
  -- \
  ':(glob)compat/**/*.py' \
  ':(glob)qwenpaw-plugin/**/*.py' \
  ':(glob)scripts/**/*.py' \
  ':(glob)scripts/**/*.sh' \
  ':(exclude)scripts/check-repository.sh'
grep_status=$?
set -e
case "$grep_status" in
  0)
    echo "A generator can mark evidence publishable." >&2
    exit 1
    ;;
  1)
    ;;
  *)
    echo "Publishable-generator scan did not execute reliably." >&2
    exit 1
    ;;
esac

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
