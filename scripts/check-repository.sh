#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

for file in upstreams.lock.json schemas/*.json config/examples/*.json; do
  jq empty "$file"
done

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
