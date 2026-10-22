#!/usr/bin/env bash
# Stub-gh checks for scripts/notify-candidate-canary.sh.
# The stub is the only gh this file runs. It never calls GitHub.
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

test_root="$(mktemp -d)"
cleanup() {
  rm -rf -- "$test_root"
}
trap cleanup EXIT

mkdir -p "$test_root/bin" "$test_root/views"
export TMPDIR="$test_root"
export PATH="$test_root/bin:${PATH}"
unset GH_TOKEN GITHUB_TOKEN || true

cat >"$test_root/bin/gh" <<'EOF'
#!/usr/bin/env bash
echo "real gh must not be called" >&2
exit 99
EOF
chmod 0755 "$test_root/bin/gh"

cat >"$test_root/bin/fake-gh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
log="${FAKE_GH_LOG:?}"
printf '%s\n' "$*" >>"$log"

save_body() {
  local previous=""
  local arg
  for arg in "$@"; do
    if [[ "$previous" == "--body-file" ]]; then
      cp -- "$arg" "${FAKE_GH_LAST_BODY:?}"
    fi
    previous="$arg"
  done
}
save_body "$@"

cmd="${1:-}"
sub="${2:-}"

if [[ "$cmd" == "run" && "$sub" == "view" ]]; then
  status="${FAKE_GH_RUN_VIEW_EXIT:-0}"
  if [[ "$status" -ne 0 ]]; then
    echo "run view failed" >&2
    exit "$status"
  fi
  printf '%s\t%s\n' "${FAKE_GH_RUN_STATUS:-in_progress}" "${FAKE_GH_RUN_CONCLUSION:-}"
  exit 0
fi

if [[ "$cmd" == "issue" && "$sub" == "list" ]]; then
  status="${FAKE_GH_LIST_EXIT:-0}"
  if [[ "$status" -ne 0 ]]; then
    echo "issue list failed" >&2
    exit "$status"
  fi
  numbers="${FAKE_GH_LIST_NUMBERS:-}"
  previous=""
  for arg in "$@"; do
    if [[ "$previous" == "--state" && "$arg" == "closed" ]]; then
      numbers="${FAKE_GH_CLOSED_NUMBERS:-}"
    fi
    previous="$arg"
  done
  if [[ -n "$numbers" ]]; then
    for number in $numbers; do
      printf '%s\n' "$number"
    done
  fi
  exit 0
fi

if [[ "$cmd" == "issue" && "$sub" == "view" ]]; then
  status="${FAKE_GH_VIEW_EXIT:-0}"
  if [[ "$status" -ne 0 ]]; then
    echo "issue view failed" >&2
    exit "$status"
  fi
  number="${3:-}"
  if [[ -n "${FAKE_GH_VIEW_DIR:-}" && -f "${FAKE_GH_VIEW_DIR}/${number}" ]]; then
    cat -- "${FAKE_GH_VIEW_DIR}/${number}"
  else
    printf '%s\n' "${FAKE_GH_VIEW_TEXT:-}"
  fi
  exit 0
fi

if [[ "$cmd" == "issue" && "$sub" == "comment" ]]; then
  exit "${FAKE_GH_COMMENT_EXIT:-0}"
fi
if [[ "$cmd" == "issue" && "$sub" == "close" ]]; then
  exit "${FAKE_GH_CLOSE_EXIT:-0}"
fi
if [[ "$cmd" == "issue" && "$sub" == "create" ]]; then
  exit "${FAKE_GH_CREATE_EXIT:-0}"
fi
if [[ "$cmd" == "label" && "$sub" == "create" ]]; then
  exit "${FAKE_GH_LABEL_EXIT:-0}"
fi

echo "unexpected gh command: $*" >&2
exit 97
EOF
chmod 0755 "$test_root/bin/fake-gh"

export FAKE_GH_LOG="$test_root/gh.log"
export FAKE_GH_LAST_BODY="$test_root/last-body"
export FAKE_GH_VIEW_DIR="$test_root/views"
export GH_BIN="$test_root/bin/fake-gh"

pass() {
  printf 'ok: %s\n' "$1"
}

fail() {
  printf 'not ok: %s\n' "$1" >&2
  exit 1
}

reset_fake() {
  : >"$FAKE_GH_LOG"
  : >"$FAKE_GH_LAST_BODY"
  rm -f -- "$test_root/views"/*
  unset FAKE_GH_RUN_VIEW_EXIT FAKE_GH_LIST_EXIT FAKE_GH_VIEW_EXIT || true
  unset FAKE_GH_CLOSED_NUMBERS || true
  unset FAKE_GH_COMMENT_EXIT FAKE_GH_CLOSE_EXIT FAKE_GH_CREATE_EXIT FAKE_GH_LABEL_EXIT || true
  export FAKE_GH_RUN_STATUS="in_progress"
  export FAKE_GH_RUN_CONCLUSION=""
  export FAKE_GH_LIST_NUMBERS=""
  export FAKE_GH_VIEW_TEXT=""
}

run_notifier() {
  local expected="$1"
  local stdout stderr status
  stdout="$(mktemp)"
  stderr="$(mktemp)"
  set +e
  env -u GH_TOKEN -u GITHUB_TOKEN \
    PATH="$PATH" \
    TMPDIR="$TMPDIR" \
    GH_BIN="$GH_BIN" \
    FAKE_GH_LOG="$FAKE_GH_LOG" \
    FAKE_GH_LAST_BODY="$FAKE_GH_LAST_BODY" \
    FAKE_GH_VIEW_DIR="$FAKE_GH_VIEW_DIR" \
    FAKE_GH_RUN_STATUS="${FAKE_GH_RUN_STATUS:-}" \
    FAKE_GH_RUN_CONCLUSION="${FAKE_GH_RUN_CONCLUSION:-}" \
    FAKE_GH_LIST_NUMBERS="${FAKE_GH_LIST_NUMBERS:-}" \
    FAKE_GH_CLOSED_NUMBERS="${FAKE_GH_CLOSED_NUMBERS:-}" \
    FAKE_GH_VIEW_TEXT="${FAKE_GH_VIEW_TEXT:-}" \
    FAKE_GH_RUN_VIEW_EXIT="${FAKE_GH_RUN_VIEW_EXIT:-0}" \
    FAKE_GH_LIST_EXIT="${FAKE_GH_LIST_EXIT:-0}" \
    FAKE_GH_VIEW_EXIT="${FAKE_GH_VIEW_EXIT:-0}" \
    FAKE_GH_COMMENT_EXIT="${FAKE_GH_COMMENT_EXIT:-0}" \
    FAKE_GH_CLOSE_EXIT="${FAKE_GH_CLOSE_EXIT:-0}" \
    FAKE_GH_CREATE_EXIT="${FAKE_GH_CREATE_EXIT:-0}" \
    FAKE_GH_LABEL_EXIT="${FAKE_GH_LABEL_EXIT:-0}" \
    GITHUB_REPOSITORY="${GITHUB_REPOSITORY:-zleo-ai/vyane-paw}" \
    GITHUB_REF="${GITHUB_REF:-refs/heads/main}" \
    GITHUB_EVENT_NAME="${GITHUB_EVENT_NAME:-schedule}" \
    CANARY_RESULT="${CANARY_RESULT:-failure}" \
    CANARY_RUN_ID="${CANARY_RUN_ID:-1000}" \
    CANARY_RUN_URL="${CANARY_RUN_URL:-https://github.com/zleo-ai/vyane-paw/actions/runs/1000}" \
    CANARY_RUN_ATTEMPT="${CANARY_RUN_ATTEMPT:-1}" \
    CANARY_RUN_TIME="${CANARY_RUN_TIME:-2026-10-22T00:00:00Z}" \
    CANARY_FAILED_STEP="${CANARY_FAILED_STEP:-Probe current vyane-rs main}" \
    CANARY_LOCK_VYANE_RS="${CANARY_LOCK_VYANE_RS:-03dbd2fd1f1a3f7d6d7f8aa9396c6ce55b5d22f0}" \
    CANARY_LOCK_RMCP="${CANARY_LOCK_RMCP:-3.0.1}" \
    CANARY_UPSTREAM_VYANE_RS="${CANARY_UPSTREAM_VYANE_RS:-03ebd40374ff37927c2d440beda7daa23f1d2aa4}" \
    CANARY_LABEL="${CANARY_LABEL:-candidate-canary-failure}" \
    bash "$repo_root/scripts/notify-candidate-canary.sh" >"$stdout" 2>"$stderr"
  status=$?
  set -e
  LAST_STDOUT="$stdout"
  LAST_STDERR="$stderr"
  LAST_STATUS="$status"
  if [[ "$status" -ne "$expected" ]]; then
    printf 'expected exit %s, got %s\n' "$expected" "$status" >&2
    printf 'stdout:\n' >&2
    cat "$stdout" >&2
    printf 'stderr:\n' >&2
    cat "$stderr" >&2
    printf 'gh log:\n' >&2
    cat "$FAKE_GH_LOG" >&2
    exit 1
  fi
}

assert_log_has() {
  local text="$1"
  local message="$2"
  if ! grep -F -q -- "$text" "$FAKE_GH_LOG"; then
    printf '%s\n' "$message" >&2
    cat "$FAKE_GH_LOG" >&2
    exit 1
  fi
}

assert_log_lacks() {
  local text="$1"
  local message="$2"
  if grep -F -q -- "$text" "$FAKE_GH_LOG"; then
    printf '%s\n' "$message" >&2
    cat "$FAKE_GH_LOG" >&2
    exit 1
  fi
}

assert_stdout_has() {
  local text="$1"
  local message="$2"
  if ! grep -F -q -- "$text" "$LAST_STDOUT"; then
    printf '%s\n' "$message" >&2
    cat "$LAST_STDOUT" >&2
    exit 1
  fi
}

assert_stdout_lacks() {
  local text="$1"
  local message="$2"
  if grep -F -q -- "$text" "$LAST_STDOUT"; then
    printf '%s\n' "$message" >&2
    cat "$LAST_STDOUT" >&2
    exit 1
  fi
}

canary_defaults() {
  export GITHUB_REPOSITORY="zleo-ai/vyane-paw"
  export GITHUB_REF="refs/heads/main"
  export GITHUB_EVENT_NAME="schedule"
  export CANARY_RESULT="failure"
  export CANARY_RUN_ID="1000"
  export CANARY_RUN_URL="https://github.com/zleo-ai/vyane-paw/actions/runs/1000"
  export CANARY_RUN_ATTEMPT="1"
  export CANARY_RUN_TIME="2026-10-22T00:00:00Z"
  export CANARY_FAILED_STEP="Probe current vyane-rs main"
  export CANARY_LOCK_VYANE_RS="03dbd2fd1f1a3f7d6d7f8aa9396c6ce55b5d22f0"
  export CANARY_LOCK_RMCP="3.0.1"
  export CANARY_UPSTREAM_VYANE_RS="03ebd40374ff37927c2d440beda7daa23f1d2aa4"
}

test_list_failure_on_failure_path() {
  reset_fake
  canary_defaults
  export FAKE_GH_LIST_EXIT=42
  run_notifier 42
  assert_log_lacks "issue create" "list failure still opened an issue"
  assert_log_lacks "issue comment" "list failure still commented"
  assert_log_lacks "issue close" "list failure still closed an issue"
  assert_stdout_lacks "no open candidate canary issue" "list failure was treated as an empty list"
  assert_stdout_lacks "opened a candidate canary issue" "list failure reported a created issue"
  pass "issue list failure on the failure path exits 42 and does not write"
}

test_list_failure_on_success_path() {
  reset_fake
  canary_defaults
  export CANARY_RESULT="success"
  export FAKE_GH_LIST_EXIT=42
  run_notifier 42
  assert_log_lacks "issue close" "success path closed issues after a failed query"
  assert_log_lacks "issue comment" "success path commented after a failed query"
  assert_stdout_lacks "no open candidate canary issue" "success path treated a failed query as an empty list"
  pass "issue list failure on the success path exits 42 and does not write"
}

test_cancelled_run_skips_writes() {
  local result
  for result in failure success; do
    reset_fake
    canary_defaults
    export CANARY_RESULT="$result"
    export FAKE_GH_RUN_STATUS="completed"
    export FAKE_GH_RUN_CONCLUSION="cancelled"
    export FAKE_GH_LIST_NUMBERS=""
    run_notifier 0
    assert_log_has "run view" "cancelled run did not query run status"
    assert_log_lacks "issue list" "cancelled run still listed issues"
    assert_log_lacks "issue create" "cancelled run opened an issue"
    assert_log_lacks "issue comment" "cancelled run commented"
    assert_log_lacks "issue close" "cancelled run closed an issue"
    assert_stdout_has "run cancelled" "cancelled run did not say it skipped the write"
    pass "cancelled run with candidate result ${result} does not write"
  done
}

test_run_view_failure_does_not_write() {
  reset_fake
  canary_defaults
  export FAKE_GH_RUN_VIEW_EXIT=42
  run_notifier 42
  assert_log_lacks "issue list" "run query failure still listed issues"
  assert_log_lacks "issue create" "run query failure still opened an issue"
  pass "run status query failure exits 42 and does not write"
}

test_newer_failure_is_not_closed() {
  reset_fake
  canary_defaults
  export CANARY_RESULT="success"
  export CANARY_RUN_ID="200"
  export CANARY_RUN_ATTEMPT="1"
  export CANARY_RUN_URL="https://github.com/zleo-ai/vyane-paw/actions/runs/200"
  export CANARY_RUN_TIME="2026-10-22T02:00:00Z"
  export FAKE_GH_LIST_NUMBERS="7"
  export FAKE_GH_VIEW_TEXT="$(printf '%s\n' \
    "- Run: https://github.com/zleo-ai/vyane-paw/actions/runs/100" \
    "- Run ID: 100" \
    "- Run attempt: 1" \
    "- Run time: 2026-10-22T01:00:00Z" \
    "- Run ID: 300" \
    "- Run attempt: 1" \
    "- Run time: 2026-10-22T03:00:00Z")"
  run_notifier 0
  assert_log_lacks "issue close" "older success closed a newer failure"
  assert_log_lacks "issue comment" "older success commented that it was closing a newer failure"
  assert_stdout_has "recorded probe 2026-10-22T03:00:00Z run 300 is newer than 2026-10-22T02:00:00Z run 200" \
    "older success did not explain the refusal"
  pass "older success does not close a newer recorded failure"
}

test_older_failure_is_closed() {
  reset_fake
  canary_defaults
  export CANARY_RESULT="success"
  export CANARY_RUN_ID="200"
  export CANARY_RUN_ATTEMPT="1"
  export CANARY_RUN_URL="https://github.com/zleo-ai/vyane-paw/actions/runs/200"
  export CANARY_RUN_TIME="2026-10-22T03:00:00Z"
  export FAKE_GH_LIST_NUMBERS="7 8"
  printf '%s\n' \
    "- Run ID: 300" \
    "- Run time: 2026-10-22T05:00:00Z" >"$test_root/views/7"
  printf '%s\n' \
    "- Run: https://github.com/zleo-ai/vyane-paw/actions/runs/50" \
    "- Run ID: 50" \
    "- Run time: 2026-10-22T01:00:00Z" >"$test_root/views/8"
  run_notifier 0
  assert_log_has "issue close 8" "newer success did not close the older failure"
  assert_log_lacks "issue close 7" "newer success closed the newer failure too"
  assert_stdout_has "left 1 open" "mixed ages were not both reported"
  if ! grep -F -q -- "- Run ID: 200" "$FAKE_GH_LAST_BODY"; then
    fail "closing comment did not record the successful run id"
  fi
  if ! grep -F -q -- "- Run time: 2026-10-22T03:00:00Z" "$FAKE_GH_LAST_BODY"; then
    fail "closing comment did not record the probe time"
  fi
  pass "newer success closes only failures that are not newer"
}

test_same_run_is_closed() {
  reset_fake
  canary_defaults
  export CANARY_RESULT="success"
  export CANARY_RUN_ID="100"
  export CANARY_RUN_ATTEMPT="1"
  export CANARY_RUN_URL="https://github.com/zleo-ai/vyane-paw/actions/runs/100"
  export CANARY_RUN_TIME="2026-10-22T02:00:00Z"
  export FAKE_GH_LIST_NUMBERS="7"
  export FAKE_GH_VIEW_TEXT="$(printf '%s\n' "- Run ID: 100" "- Run time: 2026-10-22T02:00:00Z")"
  run_notifier 0
  assert_log_has "issue close 7" "success of the same run did not close its failure notice"
  pass "the same probe may close its own failure notice"
}

test_rerun_lower_run_id_does_not_close_newer_probe() {
  reset_fake
  canary_defaults
  export CANARY_RESULT="success"
  export CANARY_RUN_ID="200"
  export CANARY_RUN_ATTEMPT="1"
  export CANARY_RUN_URL="https://github.com/zleo-ai/vyane-paw/actions/runs/200"
  export CANARY_RUN_TIME="2026-10-22T01:00:00Z"
  export FAKE_GH_LIST_NUMBERS="7"
  export FAKE_GH_VIEW_TEXT="$(printf '%s\n' \
    "- Run ID: 100" \
    "- Run attempt: 2" \
    "- Run time: 2026-10-22T03:00:00Z")"
  run_notifier 0
  assert_log_lacks "issue close" "rerun of an older run id closed a later probe"
  assert_log_lacks "issue comment" "rerun of an older run id commented a close"
  assert_stdout_has "recorded probe 2026-10-22T03:00:00Z run 100 is newer than 2026-10-22T01:00:00Z run 200" \
    "later probe on a lower run id was not treated as newer"
  pass "a later probe keeps its order when its run id is lower"
}

test_dirty_marker_lines_keep_the_newer_probe() {
  reset_fake
  canary_defaults
  export CANARY_RESULT="success"
  export CANARY_RUN_ID="200"
  export CANARY_RUN_ATTEMPT="1"
  export CANARY_RUN_URL="https://github.com/zleo-ai/vyane-paw/actions/runs/200"
  export CANARY_RUN_TIME="2026-10-22T02:00:00Z"
  export FAKE_GH_LIST_NUMBERS="7"
  export FAKE_GH_VIEW_TEXT="$(
    printf '%s\r\n' "- Run ID: 100" "- Run time: 2026-10-22T01:00:00Z"
    printf '%s \r\n' \
      "- Run: https://github.com/zleo-ai/vyane-paw/actions/runs/300" \
      "- Run ID: 300" \
      "- Run time: 2026-10-22T03:00:00Z"
  )"
  run_notifier 0
  assert_log_lacks "issue close" "dirty newer marker was ignored and the issue closed"
  assert_stdout_lacks "could not be parsed" "dirty marker was rejected instead of read"
  assert_stdout_has "recorded probe 2026-10-22T03:00:00Z run 300 is newer than 2026-10-22T02:00:00Z run 200" \
    "CRLF or trailing space hid the newer probe"
  pass "CRLF and trailing spaces still expose the newer probe"
}

test_unparsed_marker_blocks_close() {
  reset_fake
  canary_defaults
  export CANARY_RESULT="success"
  export CANARY_RUN_ID="400"
  export CANARY_RUN_ATTEMPT="1"
  export CANARY_RUN_URL="https://github.com/zleo-ai/vyane-paw/actions/runs/400"
  export CANARY_RUN_TIME="2026-10-22T04:00:00Z"
  export FAKE_GH_LIST_NUMBERS="7"
  export FAKE_GH_VIEW_TEXT="$(printf '%s\n' \
    "- Run ID: 100" \
    "- Run time: 2026-10-22T01:00:00Z" \
    "- Run ID: 300 extra")"
  run_notifier 0
  assert_log_lacks "issue close" "an unparsed marker still allowed a close"
  assert_log_lacks "issue comment" "an unparsed marker still allowed a closing comment"
  assert_stdout_has "a run marker could not be parsed" "an unparsed marker was not reported"
  pass "one unparsed marker blocks the close"
}

test_missing_run_id_is_not_closed() {
  reset_fake
  canary_defaults
  export CANARY_RESULT="success"
  export CANARY_RUN_ID="200"
  export CANARY_RUN_URL="https://github.com/zleo-ai/vyane-paw/actions/runs/200"
  export FAKE_GH_LIST_NUMBERS="7"
  export FAKE_GH_VIEW_TEXT="The candidate compatibility canary failed."
  run_notifier 0
  assert_log_lacks "issue close" "success closed an issue with no recorded run"
  assert_stdout_has "no recorded run id" "missing run id was not refused"
  pass "an issue with no recorded run id stays open"
}

test_run_url_without_probe_time_is_not_closed() {
  reset_fake
  canary_defaults
  export CANARY_RESULT="success"
  export CANARY_RUN_ID="150"
  export CANARY_RUN_ATTEMPT="1"
  export CANARY_RUN_URL="https://github.com/zleo-ai/vyane-paw/actions/runs/150"
  export CANARY_RUN_TIME="2026-10-22T04:00:00Z"
  export FAKE_GH_LIST_NUMBERS="7"
  export FAKE_GH_VIEW_TEXT="- Run: https://github.com/zleo-ai/vyane-paw/actions/runs/50"
  run_notifier 0
  assert_log_lacks "issue close" "url without a probe time was closed by run id order"
  assert_stdout_has "recorded run 50 has no probe time" "url without a probe time was not refused"
  pass "a run url without a probe time does not authorize a close"
}

test_run_url_probe_time_orders_old_notices() {
  reset_fake
  canary_defaults
  export CANARY_RESULT="success"
  export CANARY_RUN_ID="150"
  export CANARY_RUN_ATTEMPT="1"
  export CANARY_RUN_URL="https://github.com/zleo-ai/vyane-paw/actions/runs/150"
  export CANARY_RUN_TIME="2026-10-22T02:00:00Z"
  export FAKE_GH_LIST_NUMBERS="7"
  export FAKE_GH_VIEW_TEXT="$(printf '%s\n' \
    "- Run: https://github.com/zleo-ai/vyane-paw/actions/runs/180" \
    "- Run time: 2026-10-22T03:00:00Z")"
  run_notifier 0
  assert_log_lacks "issue close" "url-only newer failure was closed"
  assert_stdout_has "recorded probe 2026-10-22T03:00:00Z run 180 is newer than 2026-10-22T02:00:00Z run 150" \
    "url fallback did not supply the run id"
  pass "a run url with a probe time still blocks an older close"
}

test_unresolved_probe_time_is_not_closed() {
  reset_fake
  canary_defaults
  export CANARY_RESULT="success"
  export CANARY_RUN_ID="200"
  export CANARY_RUN_ATTEMPT="1"
  export CANARY_RUN_URL="https://github.com/zleo-ai/vyane-paw/actions/runs/200"
  export CANARY_RUN_TIME="not-a-time"
  export FAKE_GH_LIST_NUMBERS="7"
  export FAKE_GH_VIEW_TEXT="$(printf '%s\n' \
    "- Run ID: 50" \
    "- Run time: 2026-10-22T01:00:00Z")"
  run_notifier 0
  assert_log_lacks "issue close" "unresolved probe time fell back to run id order"
  assert_stdout_has "this probe time is unresolved" "unresolved probe time was not refused"
  pass "a success without a probe time does not close"
}

test_failure_records_run_and_creates_one_issue() {
  reset_fake
  canary_defaults
  run_notifier 0
  assert_log_has "label create" "failure with an empty list did not ensure the label"
  assert_log_has "issue create" "failure with an empty list did not open an issue"
  if ! grep -F -q -- "- Run ID: 1000" "$FAKE_GH_LAST_BODY"; then
    fail "failure notice did not record the run id"
  fi
  if ! grep -F -q -- "- Run attempt: 1" "$FAKE_GH_LAST_BODY"; then
    fail "failure notice did not record the probe attempt"
  fi
  if ! grep -F -q -- "- Run time: 2026-10-22T00:00:00Z" "$FAKE_GH_LAST_BODY"; then
    fail "failure notice did not record the probe time"
  fi
  pass "failure with no open issue records the probe identity and opens one issue"
}

test_older_failure_does_not_reopen_a_newer_probe() {
  reset_fake
  canary_defaults
  export CANARY_RESULT="failure"
  export CANARY_RUN_ID="100"
  export CANARY_RUN_ATTEMPT="2"
  export CANARY_RUN_URL="https://github.com/zleo-ai/vyane-paw/actions/runs/100"
  export CANARY_RUN_TIME="2026-10-22T01:00:00Z"
  export FAKE_GH_LIST_NUMBERS=""
  export FAKE_GH_CLOSED_NUMBERS="9"
  printf '%s\n' \
    "- Run ID: 200" \
    "- Run attempt: 1" \
    "- Run time: 2026-10-22T03:00:00Z" >"$test_root/views/9"
  run_notifier 0
  assert_log_lacks "issue create" "older failure opened a new issue after a newer probe"
  assert_log_lacks "issue comment" "older failure commented after a newer probe"
  assert_log_has "issue view 9" "older failure did not read the closed notice"
  assert_stdout_has "recorded probe 2026-10-22T03:00:00Z run 200 is newer than 2026-10-22T01:00:00Z run 100" \
    "older failure did not explain why it stayed closed"
  pass "an older failure does not open a new issue over a newer recorded probe"
}

test_failure_comments_instead_of_creating() {
  reset_fake
  canary_defaults
  export FAKE_GH_LIST_NUMBERS="4"
  run_notifier 0
  assert_log_has "issue comment 4" "failure did not comment on the open issue"
  assert_log_lacks "issue create" "failure opened a second issue"
  pass "failure with an open issue only comments"
}

test_skip_and_field_guards() {
  reset_fake
  canary_defaults
  export GITHUB_REPOSITORY="someone/fork"
  run_notifier 0
  if [[ -s "$FAKE_GH_LOG" ]]; then
    fail "wrong repository called gh"
  fi
  pass "wrong repository skips without calling gh"

  reset_fake
  canary_defaults
  export CANARY_RUN_URL='https://evil.example/$(id)'
  export CANARY_FAILED_STEP=$'Probe\ncurrent'
  run_notifier 0
  if grep -F -q -- "evil.example" "$FAKE_GH_LAST_BODY" || grep -F -q -- '$(id)' "$FAKE_GH_LAST_BODY"; then
    fail "unsafe run url was copied into the issue body"
  fi
  if grep -F -q -- $'Probe\ncurrent' "$FAKE_GH_LAST_BODY"; then
    fail "multiline step name was copied into the issue body"
  fi
  if ! grep -F -q -- "- Run: unresolved" "$FAKE_GH_LAST_BODY"; then
    fail "unsafe run url was not replaced"
  fi
  if ! grep -F -q -- "- Failed step: unresolved" "$FAKE_GH_LAST_BODY"; then
    fail "multiline step name was not replaced"
  fi
  pass "unsafe url and multiline step name become unresolved"

  reset_fake
  canary_defaults
  export FAKE_GH_CREATE_EXIT=7
  run_notifier 7
  pass "issue create failure exits 7"
}

test_workflow_notify_serialization_and_cancellation() {
  python3 - "$repo_root/.github/workflows/candidate-compatibility.yml" <<'PY'
import sys
from pathlib import Path

lines = Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()
top = []
for line in lines:
    if not line.strip() or line.lstrip().startswith("#") or line[0].isspace():
        continue
    top.append(line.split(":", 1)[0])
if "concurrency" in top:
    sys.exit("workflow-level concurrency would cancel notify together with the probe")

def job(name: str) -> list[str]:
    start = lines.index(f"  {name}:")
    end = len(lines)
    for index in range(start + 1, len(lines)):
        candidate = lines[index]
        if (
            candidate.startswith("  ")
            and not candidate.startswith("   ")
            and candidate.endswith(":")
        ):
            end = index
            break
    return lines[start:end]

def before_steps(block: list[str]) -> str:
    kept = []
    for line in block:
        if line.startswith("    steps:"):
            break
        kept.append(line)
    return "\n".join(kept)

candidate = before_steps(job("candidate"))
notify = job("notify")
notify_head = before_steps(notify)
if "group: vyane-rs-candidate-compatibility" not in candidate:
    sys.exit("candidate lost its own concurrency group")
if "cancel-in-progress: true" not in candidate:
    sys.exit("candidate probe is no longer cancelled when a newer run starts")
if "group: vyane-rs-candidate-canary-notify" not in notify_head:
    sys.exit("notify has no separate concurrency group")
if "cancel-in-progress: false" not in notify_head:
    sys.exit("notify concurrency cancels an in-progress writer")
if "vyane-rs-candidate-compatibility" in notify_head:
    sys.exit("notify is still in the probe cancellation group")
if "!cancelled()" not in notify_head:
    sys.exit("notify job still starts after the run is cancelled")
window = []
for index, line in enumerate(notify):
    if "Update candidate canary issue" in line:
        window = notify[index : index + 8]
        break
if not window or not any("!cancelled()" in line for line in window):
    sys.exit("issue-writing step does not stop when the run is cancelled")
if "actions: read" not in notify_head:
    sys.exit("notify cannot read run status")
if "issues: write" not in notify_head:
    sys.exit("notify lost issues: write")
print("workflow notify gate ok")
PY
  pass "notify writes are serialized and a cancelled run does not keep the writer"
}

test_notify_queue_keeps_pending() {
  python3 - "$repo_root/.github/workflows/candidate-compatibility.yml" <<'PY'
import sys
from pathlib import Path

lines = Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()
start = lines.index("  notify:")
end = len(lines)
for index in range(start + 1, len(lines)):
    candidate = lines[index]
    if (
        candidate.startswith("  ")
        and not candidate.startswith("   ")
        and candidate.endswith(":")
    ):
        end = index
        break
head = []
for line in lines[start:end]:
    if line.startswith("    steps:"):
        break
    head.append(line)
text = "\n".join(head)
if "group: vyane-rs-candidate-canary-notify" not in text:
    sys.exit("notify has no separate concurrency group")
if "cancel-in-progress: false" not in text:
    sys.exit("notify concurrency cancels an in-progress writer")
if "queue: max" not in text or "queue: single" in text:
    sys.exit("notify queue keeps only one pending run")
print("notify queue gate ok")
PY
  pass "notify keeps waiting runs instead of replacing the one pending run"
}

test_probe_identity_comes_from_the_candidate_job() {
  python3 - "$repo_root/.github/workflows/candidate-compatibility.yml" <<'PY'
import sys
from pathlib import Path

lines = Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()

def job(name: str) -> list[str]:
    start = lines.index(f"  {name}:")
    end = len(lines)
    for index in range(start + 1, len(lines)):
        candidate = lines[index]
        if (
            candidate.startswith("  ")
            and not candidate.startswith("   ")
            and candidate.endswith(":")
        ):
            end = index
            break
    return lines[start:end]

candidate = "\n".join(job("candidate"))
notify = "\n".join(job("notify"))
if "echo \"attempt=${{ github.run_attempt }}\"" not in candidate:
    sys.exit("candidate does not snapshot github.run_attempt when the probe starts")
if "run_attempt: ${{ steps.start.outputs.attempt }}" not in candidate:
    sys.exit("candidate does not publish the snapshotted probe attempt")
if "CANARY_RUN_ATTEMPT: ${{ needs.candidate.outputs.run_attempt }}" not in notify:
    sys.exit("notify does not keep the candidate probe attempt")
if "CANARY_RUN_ATTEMPT: ${{ github.run_attempt }}" in notify:
    sys.exit("notify uses the live run attempt, which changes on a notify-only re-run")
if "CANARY_RUN_TIME: ${{ needs.candidate.outputs.started_at }}" not in notify:
    sys.exit("notify does not keep the candidate probe start time")
print("probe identity gate ok")
PY
  pass "notify reuses the probe attempt and start time from the candidate job"
}

test_status_cancellation_is_qualified() {
  python3 - "$repo_root/docs/STATUS.md" <<'PY'
import sys
from pathlib import Path

text = " ".join(Path(sys.argv[1]).read_text(encoding="utf-8").split())
if "A cancelled run does not write an issue." in text:
    sys.exit("STATUS still guarantees that a cancelled run writes nothing")
if "cancelled before the issue-writing step starts does not write" not in text:
    sys.exit("STATUS does not limit the no-write claim to cancellation before the step")
if "already been sent is not withdrawn" not in text:
    sys.exit("STATUS does not say an in-flight issue request can still land")
print("status cancellation wording ok")
PY
  pass "STATUS limits the cancellation claim to the step boundary"
}

test_workflow_probe_timeout() {
  python3 - "$repo_root/.github/workflows/candidate-compatibility.yml" <<'PY'
import sys
from pathlib import Path

lines = Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()
start = lines.index("  candidate:")
end = lines.index("  notify:")
block = lines[start:end]
job_timeout = None
probe_timeout = None
seen_probe = False
seen_cancelled_outcome = False
for line in block:
    stripped = line.strip()
    if line.startswith("    timeout-minutes:") and job_timeout is None:
        job_timeout = int(stripped.split(":", 1)[1].strip())
    if stripped == "id: probe":
        seen_probe = True
        continue
    if seen_probe and stripped.startswith("timeout-minutes:"):
        probe_timeout = int(stripped.split(":", 1)[1].strip())
        seen_probe = False
    if 'steps.probe.outcome' in line and "cancelled" in line:
        seen_cancelled_outcome = True
if job_timeout is None or probe_timeout is None:
    sys.exit(f"missing timeout: job={job_timeout} probe={probe_timeout}")
if probe_timeout >= job_timeout:
    sys.exit(f"probe timeout {probe_timeout} is not shorter than job timeout {job_timeout}")
if not seen_cancelled_outcome:
    sys.exit("a cancelled probe step is not recorded as the failed step")
print(f"probe timeout {probe_timeout} < job timeout {job_timeout}")
PY
  pass "probe step times out before the job cap and still names that step"
}

test_list_failure_on_failure_path
test_list_failure_on_success_path
test_cancelled_run_skips_writes
test_run_view_failure_does_not_write
test_newer_failure_is_not_closed
test_older_failure_is_closed
test_same_run_is_closed
test_rerun_lower_run_id_does_not_close_newer_probe
test_dirty_marker_lines_keep_the_newer_probe
test_unparsed_marker_blocks_close
test_missing_run_id_is_not_closed
test_run_url_without_probe_time_is_not_closed
test_run_url_probe_time_orders_old_notices
test_unresolved_probe_time_is_not_closed
test_failure_records_run_and_creates_one_issue
test_older_failure_does_not_reopen_a_newer_probe
test_failure_comments_instead_of_creating
test_skip_and_field_guards
test_workflow_notify_serialization_and_cancellation
test_notify_queue_keeps_pending
test_probe_identity_comes_from_the_candidate_job
test_status_cancellation_is_qualified
test_workflow_probe_timeout

printf 'notify candidate canary checks passed\n'
