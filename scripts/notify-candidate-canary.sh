#!/usr/bin/env bash
# Open, comment on, or close the candidate-canary failure issue.
# The body is only a run link, run id, run time, failed step name, and revisions.
# Issue queries must succeed before they are parsed. A cancelled run does not
# write. An older successful run does not close a newer failure.
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

strip_zeros() {
  local value="$1"
  while [[ "$value" == 0* && ${#value} -gt 1 ]]; do
    value="${value#0}"
  done
  printf '%s\n' "$value"
}

# Return 0 when the decimal integer in $1 is strictly greater than $2.
decimal_gt() {
  local left right i left_digit right_digit
  if [[ ! "$1" =~ ^[0-9]+$ || ! "$2" =~ ^[0-9]+$ ]]; then
    return 2
  fi
  left="$(strip_zeros "$1")"
  right="$(strip_zeros "$2")"
  if [[ ${#left} -gt ${#right} ]]; then
    return 0
  fi
  if [[ ${#left} -lt ${#right} ]]; then
    return 1
  fi
  for ((i = 0; i < ${#left}; i++)); do
    left_digit="${left:i:1}"
    right_digit="${right:i:1}"
    if [[ "$left_digit" -gt "$right_digit" ]]; then
      return 0
    fi
    if [[ "$left_digit" -lt "$right_digit" ]]; then
      return 1
    fi
  done
  return 1
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
run_id="${CANARY_RUN_ID:-}"
if [[ ! "$run_id" =~ ^[0-9]+$ ]]; then
  echo "unsupported canary run id" >&2
  exit 1
fi
if [[ "$run_url" != "unresolved" && "${run_url##*/}" != "$run_id" ]]; then
  echo "canary run id does not match run url" >&2
  exit 1
fi

failed_step="unresolved"
case "${CANARY_FAILED_STEP:-}" in
  "Checkout repository" | "Set up uv" | "Probe current vyane-rs main")
    failed_step="${CANARY_FAILED_STEP}"
    ;;
esac

work_dir="$(mktemp -d)"
cleanup() {
  rm -rf -- "$work_dir"
}
trap cleanup EXIT
body_file="$work_dir/body"

if [[ "$result" == "failure" ]]; then
  cat >"$body_file" <<EOF
The candidate compatibility canary failed.

- Run: ${run_url}
- Run ID: ${run_id}
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
- Run ID: ${run_id}
- Run time: ${run_time}
- Locked vyane-rs: ${lock_vyane}
- Locked rmcp: ${lock_rmcp}
- Upstream vyane-rs main: ${upstream_vyane}
EOF
fi

# Check the command status before reading its output. A process substitution
# would hide a non-zero gh exit from mapfile and from set -e.
capture_gh() {
  local output="$1"
  local failure_message="$2"
  shift 2
  set +e
  "$gh_bin" "$@" >"$output"
  local status=$?
  set -e
  if [[ "$status" -ne 0 ]]; then
    printf '%s\n' "$failure_message" >&2
    exit "$status"
  fi
}

run_file="$work_dir/run"
capture_gh "$run_file" "candidate canary run query failed" \
  run view "$run_id" \
  --repo "$repo" \
  --json status,conclusion \
  --jq '[.status, (.conclusion // "")] | @tsv'

run_lines=()
mapfile -t run_lines <"$run_file"
if [[ "${#run_lines[@]}" -ne 1 ]]; then
  echo "candidate canary run query returned an unexpected status" >&2
  exit 1
fi
run_line="${run_lines[0]}"
if [[ "$run_line" != *$'\t'* ]]; then
  echo "candidate canary run query returned an unexpected status" >&2
  exit 1
fi
run_status="${run_line%%$'\t'*}"
run_conclusion="${run_line#*$'\t'}"
if [[ "$run_conclusion" == *$'\t'* ]]; then
  echo "candidate canary run query returned an unexpected status" >&2
  exit 1
fi
case "$run_status" in
  queued | in_progress | completed | waiting | requested | pending) ;;
  *)
    echo "candidate canary run query returned an unexpected status" >&2
    exit 1
    ;;
esac
case "$run_conclusion" in
  "" | success | failure | cancelled | skipped | timed_out | neutral | action_required | stale | startup_failure) ;;
  *)
    echo "candidate canary run query returned an unexpected status" >&2
    exit 1
    ;;
esac
if [[ "$run_status" == "cancelled" || "$run_conclusion" == "cancelled" ]]; then
  echo "candidate canary issue write skipped: run cancelled"
  exit 0
fi

list_file="$work_dir/issues"
capture_gh "$list_file" "candidate canary issue query failed" \
  issue list \
  --repo "$repo" \
  --label "$label" \
  --state open \
  --limit 30 \
  --json number \
  --jq '.[].number'

open_issues=()
mapfile -t open_issues <"$list_file"
numbers=()
if [[ "${#open_issues[@]}" -gt 0 ]]; then
  for number in "${open_issues[@]}"; do
    if [[ "$number" =~ ^[0-9]+$ ]]; then
      numbers+=("$number")
    fi
  done
fi

# Newest run id recorded in the issue body or comments. Empty when none match.
newest_recorded_run() {
  local file="$1"
  local line recorded newest=""
  while IFS= read -r line || [[ -n "$line" ]]; do
    recorded=""
    if [[ "$line" =~ ^-\ Run\ ID:\ ([0-9]+)$ ]]; then
      recorded="${BASH_REMATCH[1]}"
    elif [[ "$line" =~ ^-\ Run:\ https://github\.com/zleo-ai/vyane-paw/actions/runs/([0-9]+)$ ]]; then
      recorded="${BASH_REMATCH[1]}"
    fi
    if [[ -n "$recorded" ]]; then
      if [[ -z "$newest" ]] || decimal_gt "$recorded" "$newest"; then
        newest="$recorded"
      fi
    fi
  done <"$file"
  printf '%s\n' "$newest"
}

if [[ "$result" == "success" ]]; then
  if [[ "${#numbers[@]}" -eq 0 ]]; then
    echo "no open candidate canary issue"
    exit 0
  fi
  closed=0
  refused=0
  for number in "${numbers[@]}"; do
    view_file="$work_dir/issue-$number"
    capture_gh "$view_file" "candidate canary issue read failed" \
      issue view "$number" \
      --repo "$repo" \
      --json body,comments \
      --jq '[.body, (.comments[].body // empty)] | join("\n")'
    recorded="$(newest_recorded_run "$view_file")"
    if [[ -z "$recorded" ]]; then
      echo "refusing to close issue ${number}: no recorded run id"
      refused=$((refused + 1))
      continue
    fi
    if decimal_gt "$recorded" "$run_id"; then
      echo "refusing to close issue ${number}: recorded run ${recorded} is newer than ${run_id}"
      refused=$((refused + 1))
      continue
    fi
    "$gh_bin" issue comment "$number" --repo "$repo" --body-file "$body_file"
    "$gh_bin" issue close "$number" --repo "$repo" --reason completed
    closed=$((closed + 1))
  done
  if [[ "$refused" -eq 0 ]]; then
    echo "closed ${closed} candidate canary issue(s)"
  else
    echo "closed ${closed} candidate canary issue(s); left ${refused} open"
  fi
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
