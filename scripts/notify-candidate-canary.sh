#!/usr/bin/env bash
# Open, comment on, or close the candidate-canary failure issue.
# The body is only a run link, run id, probe attempt, probe start time,
# failed step name, and revisions.
# Issue queries must succeed before they are parsed. A cancelled run does not
# reach a write. A success closes an issue only when every recorded probe
# marker parses and none of those probe starts is later than this probe.
# Run id order is not used: a re-run keeps the same run id.
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

# Drop a trailing CR and any other trailing whitespace so an edited marker
# still parses. Leading text is left alone.
trim_trailing_space() {
  local line="$1"
  line="${line%"${line##*[![:space:]]}"}"
  printf '%s\n' "$line"
}

# Byte order of the fixed UTC stamp. Return 0 when $1 is later than $2.
probe_time_is_newer() {
  local left="$1"
  local right="$2"
  local sorted
  if [[ "$left" == "$right" ]]; then
    return 1
  fi
  sorted="$(printf '%s\n%s\n' "$left" "$right" | LC_ALL=C sort)"
  [[ "${sorted%%$'\n'*}" == "$right" ]]
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
# Attempt captured when the probe started. A notify-only re-run must pass
# that same value; github.run_attempt would name the later notify attempt.
run_attempt="$(
  exact_field "${CANARY_RUN_ATTEMPT:-}" '^[0-9]+$' "unresolved"
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
- Run attempt: ${run_attempt}
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
- Run attempt: ${run_attempt}
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

# Reset the marker currently being assembled. Dynamic scope: callers keep
# these names local, and this helper writes those locals.
reset_probe_record() {
  record_seen=0
  record_bad=0
  record_run_id=""
  record_attempt=""
  record_time=""
}

# Write one finished marker. A marker that does not parse is kept as
# parse-error so a later, readable marker cannot authorize a close.
flush_probe_record() {
  local dest="$1"
  if [[ "$record_seen" -eq 0 ]]; then
    return 0
  fi
  if [[ "$record_bad" -ne 0 || -z "$record_run_id" ]]; then
    printf 'parse-error - - -\n' >>"$dest"
  elif [[ -z "$record_time" ]]; then
    printf 'no-time - %s -\n' "$record_run_id" >>"$dest"
  else
    printf 'probe %s %s %s\n' "$record_time" "$record_run_id" "${record_attempt:--}" >>"$dest"
  fi
  reset_probe_record
}

# Append one line per probe marker in $1 to $2:
#   probe <time> <run_id> <attempt|->
#   no-time - <run_id> -
#   parse-error - - -
# Trailing CR and trailing whitespace are not part of the marker. Any marker
# line that still does not match is a parse error.
collect_probe_records() {
  local file="$1"
  local dest="$2"
  local line trimmed new_id
  reset_probe_record
  while IFS= read -r line || [[ -n "$line" ]]; do
    trimmed="$(trim_trailing_space "$line")"
    if [[ "$trimmed" == "- Run ID:"* ]]; then
      if [[ "$trimmed" =~ ^-\ Run\ ID:\ ([0-9]+)$ ]]; then
        new_id="${BASH_REMATCH[1]}"
        if [[ -n "$record_run_id" && "$record_run_id" != "$new_id" ]]; then
          flush_probe_record "$dest"
        fi
        record_seen=1
        record_run_id="$new_id"
      else
        if [[ "$record_seen" -ne 0 ]]; then
          flush_probe_record "$dest"
        fi
        record_seen=1
        record_bad=1
      fi
    elif [[ "$trimmed" == "- Run attempt:"* ]]; then
      record_seen=1
      if [[ -n "$record_attempt" ]]; then
        flush_probe_record "$dest"
        record_seen=1
        record_bad=1
      elif [[ "$trimmed" =~ ^-\ Run\ attempt:\ ([0-9]+)$ ]]; then
        record_attempt="${BASH_REMATCH[1]}"
      elif [[ "$trimmed" == "- Run attempt: unresolved" ]]; then
        record_attempt="-"
      else
        record_bad=1
      fi
    elif [[ "$trimmed" == "- Run time:"* ]]; then
      record_seen=1
      if [[ -n "$record_time" ]]; then
        flush_probe_record "$dest"
        record_seen=1
        record_bad=1
      elif [[ "$trimmed" =~ ^-\ Run\ time:\ ([0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z)$ ]]; then
        record_time="${BASH_REMATCH[1]}"
      elif [[ "$trimmed" == "- Run time: unresolved" ]]; then
        :
      else
        record_bad=1
      fi
    elif [[ "$trimmed" == "- Run:"* ]]; then
      if [[ "$record_seen" -ne 0 ]]; then
        flush_probe_record "$dest"
      fi
      record_seen=1
      if [[ "$trimmed" == "- Run: unresolved" ]]; then
        :
      elif [[ "$trimmed" =~ ^-\ Run:\ https://github\.com/zleo-ai/vyane-paw/actions/runs/([0-9]+)$ ]]; then
        new_id="${BASH_REMATCH[1]}"
        if [[ -z "$record_run_id" ]]; then
          record_run_id="$new_id"
        elif [[ "$record_run_id" != "$new_id" ]]; then
          record_bad=1
        fi
      else
        record_bad=1
      fi
    fi
  done <"$file"
  flush_probe_record "$dest"
}

# Return 0 when this success may close the issue. Otherwise print the reason
# and return 1. One unparsable marker blocks the close even if another marker
# is an older, readable failure.
success_may_close() {
  local number="$1"
  local view_file="$2"
  local record_file="$3"
  local line kind rec_time rec_id
  : >"$record_file"
  if [[ "$run_time" == "unresolved" ]]; then
    echo "refusing to close issue ${number}: this probe time is unresolved"
    return 1
  fi
  collect_probe_records "$view_file" "$record_file"
  if [[ ! -s "$record_file" ]]; then
    echo "refusing to close issue ${number}: no recorded run id"
    return 1
  fi
  while read -r kind rec_time rec_id _; do
    if [[ "$kind" == "parse-error" ]]; then
      echo "refusing to close issue ${number}: a run marker could not be parsed"
      return 1
    fi
  done <"$record_file"
  while read -r kind rec_time rec_id _; do
    if [[ "$kind" == "no-time" ]]; then
      echo "refusing to close issue ${number}: recorded run ${rec_id} has no probe time"
      return 1
    fi
  done <"$record_file"
  while read -r kind rec_time rec_id _; do
    [[ "$kind" == "probe" ]] || continue
    if probe_time_is_newer "$rec_time" "$run_time"; then
      echo "refusing to close issue ${number}: recorded probe ${rec_time} run ${rec_id} is newer than ${run_time} run ${run_id}"
      return 1
    fi
    if [[ "$rec_time" == "$run_time" && "$rec_id" != "$run_id" ]]; then
      echo "refusing to close issue ${number}: recorded probe ${rec_time} run ${rec_id} ties this probe but is another run"
      return 1
    fi
  done <"$record_file"
  return 0
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
    if ! success_may_close "$number" "$view_file" "$work_dir/records-$number"; then
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

# A notify that waited behind a newer probe must not open a fresh issue
# after that newer probe already closed the previous one.
closed_file="$work_dir/closed-issues"
capture_gh "$closed_file" "candidate canary issue query failed" \
  issue list \
  --repo "$repo" \
  --label "$label" \
  --state closed \
  --limit 30 \
  --json number \
  --jq '.[].number'
closed_issues=()
mapfile -t closed_issues <"$closed_file"
if [[ "$run_time" != "unresolved" && "${#closed_issues[@]}" -gt 0 ]]; then
  for number in "${closed_issues[@]}"; do
    [[ "$number" =~ ^[0-9]+$ ]] || continue
    closed_view="$work_dir/closed-$number"
    capture_gh "$closed_view" "candidate canary issue read failed" \
      issue view "$number" \
      --repo "$repo" \
      --json body,comments \
      --jq '[.body, (.comments[].body // empty)] | join("\n")'
    closed_records="$work_dir/closed-records-$number"
    : >"$closed_records"
    collect_probe_records "$closed_view" "$closed_records"
    while read -r kind rec_time rec_id _; do
      [[ "$kind" == "probe" ]] || continue
      if probe_time_is_newer "$rec_time" "$run_time"; then
        echo "not opening a candidate canary issue: recorded probe ${rec_time} run ${rec_id} is newer than ${run_time} run ${run_id}"
        exit 0
      fi
    done <"$closed_records"
  done
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
