#!/usr/bin/env bash
# Open, comment on, or close the candidate-canary failure issue.
# The body is only a run link, run time, failed step name, and revisions.
set -euo pipefail

expected_repo="zleo-ai/vyane-paw"
label="${CANARY_LABEL:-candidate-canary-failure}"
gh_bin="${GH_BIN:-gh}"

repo="${GITHUB_REPOSITORY:-}"
ref="${GITHUB_REF:-}"
event="${GITHUB_EVENT_NAME:-}"
result="${CANARY_RESULT:-}"

if [[ "$repo" != "$expected_repo" || "$ref" != "refs/heads/main" ]]; then
  echo "candidate canary issue write skipped"
  exit 0
fi
if [[ "$event" != "schedule" && "$event" != "workflow_dispatch" ]]; then
  echo "candidate canary issue write skipped"
  exit 0
fi

case "$result" in
  success | failure) ;;
  *)
    echo "unsupported canary result" >&2
    exit 1
    ;;
esac

exact_field() {
  local value="$1"
  local pattern="$2"
  local fallback="$3"
  if [[ "$value" =~ $pattern ]]; then
    printf '%s\n' "$value"
  else
    printf '%s\n' "$fallback"
  fi
}

lock_vyane="$(
  exact_field "${CANARY_LOCK_VYANE_RS:-}" '^[0-9a-f]{40}$' "unresolved"
)"
lock_rmcp="$(
  exact_field "${CANARY_LOCK_RMCP:-}" '^[0-9]+\.[0-9]+\.[0-9]+$' "unresolved"
)"
upstream_vyane="$(
  exact_field "${CANARY_UPSTREAM_VYANE_RS:-}" '^[0-9a-f]{40}$' "unresolved"
)"
run_time="$(
  exact_field "${CANARY_RUN_TIME:-}" \
    '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$' \
    "unresolved"
)"
run_url="$(
  exact_field "${CANARY_RUN_URL:-}" \
    '^https://github\.com/zleo-ai/vyane-paw/actions/runs/[0-9]+$' \
    "unresolved"
)"

failed_step="unresolved"
case "${CANARY_FAILED_STEP:-}" in
  "Checkout repository" | "Set up uv" | "Probe current vyane-rs main")
    failed_step="${CANARY_FAILED_STEP}"
    ;;
esac

body_file="$(mktemp)"
cleanup() {
  rm -f -- "$body_file"
}
trap cleanup EXIT

if [[ "$result" == "failure" ]]; then
  cat >"$body_file" <<EOF
The candidate compatibility canary failed.

- Run: ${run_url}
- Run time: ${run_time}
- Failed step: ${failed_step}
- Locked vyane-rs: ${lock_vyane}
- Locked rmcp: ${lock_rmcp}
- Upstream vyane-rs main: ${upstream_vyane}
EOF
else
  cat >"$body_file" <<EOF
The candidate compatibility canary passed. Closing this failure notice.

- Run: ${run_url}
- Run time: ${run_time}
- Locked vyane-rs: ${lock_vyane}
- Locked rmcp: ${lock_rmcp}
- Upstream vyane-rs main: ${upstream_vyane}
EOF
fi

mapfile -t open_issues < <(
  "$gh_bin" issue list \
    --repo "$repo" \
    --label "$label" \
    --state open \
    --limit 30 \
    --json number \
    --jq '.[].number'
)

numbers=()
if [[ "${#open_issues[@]}" -gt 0 ]]; then
  for number in "${open_issues[@]}"; do
    if [[ "$number" =~ ^[0-9]+$ ]]; then
      numbers+=("$number")
    fi
  done
fi

if [[ "$result" == "success" ]]; then
  if [[ "${#numbers[@]}" -eq 0 ]]; then
    echo "no open candidate canary issue"
    exit 0
  fi
  for number in "${numbers[@]}"; do
    "$gh_bin" issue comment "$number" --repo "$repo" --body-file "$body_file"
    "$gh_bin" issue close "$number" --repo "$repo" --reason completed
  done
  echo "closed ${#numbers[@]} candidate canary issue(s)"
  exit 0
fi

if [[ "${#numbers[@]}" -gt 0 ]]; then
  for number in "${numbers[@]}"; do
    "$gh_bin" issue comment "$number" --repo "$repo" --body-file "$body_file"
  done
  echo "commented on ${#numbers[@]} open candidate canary issue(s)"
  exit 0
fi

"$gh_bin" label create "$label" \
  --repo "$repo" \
  --color B60205 \
  --description "Scheduled or manually dispatched candidate canary failed" \
  --force
"$gh_bin" issue create \
  --repo "$repo" \
  --label "$label" \
  --title "Candidate canary failed" \
  --body-file "$body_file"
echo "opened a candidate canary issue"
