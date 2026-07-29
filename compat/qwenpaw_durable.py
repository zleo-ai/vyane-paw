#!/usr/bin/env python3
"""Headless durable-workflow integration through pinned QwenPaw and Vyane."""

from __future__ import annotations

import argparse
import json
import os
import stat
import subprocess
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from demo_flows import EndpointState, RunningEndpoint
from qwenpaw_app import (
    MCP_CLIENT_KEY,
    SENSITIVE_ENV_NAMES,
    free_port,
    install_plugin,
    request,
    start_app,
    stop_app,
    wait_for_health,
    wait_for_mcp_tools,
    wait_for_pid_file,
    wait_for_plugin_command,
    wait_for_process_exit,
    wait_for_task,
)


DURABLE_TOOLS = [
    "vyane_broadcast",
    "vyane_dispatch",
    "vyane_route",
    "vyane_workflow_cancel",
    "vyane_workflow_status",
    "vyane_workflow_submit",
]
DURABLE_TASK = "DURABLE_WORKFLOW_TASK_MUST_NOT_ENTER_LOGS"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plugin-dir", type=Path, required=True)
    parser.add_argument("--launcher", type=Path, required=True)
    parser.add_argument("--vyane-bin", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--upstreams-lock", type=Path, required=True)
    parser.add_argument("--vyane-revision", required=True)
    parser.add_argument("--rmcp-version", required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    return parser.parse_args()


def write_config(path: Path, endpoint: RunningEndpoint) -> None:
    path.write_text(
        f"""
[providers.synthetic]
base_url = "{endpoint.url}"
auth_style = "bearer"
protocol = "openai_chat"
default_model = "synthetic-model"

[profiles.slow]
provider = "synthetic"
protocol = "openai_chat"
harness = "none"
model = "synthetic-model"
tier = "economy"
""".strip()
        + "\n",
        encoding="utf-8",
    )


def write_policy(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "0.1.0",
                "profile": "durable-test",
                "allowed_tools": DURABLE_TOOLS,
                "allow_failover": False,
                "allow_broadcast": False,
                "allow_durable_workflows": True,
                "max_parallel_targets": 1,
                "allowed_targets": ["slow"],
            },
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )


def write_mcp_wrapper(root: Path, launcher: Path) -> Path:
    pid_path = root / "vyane-mcp.pid"
    wrapper = root / "launch-vyane-paw-mcp.sh"
    wrapper.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$$" >"{pid_path}"
exec "{launcher}"
""",
        encoding="utf-8",
    )
    wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR)
    return wrapper


def run_cli(
    binary: Path,
    config: Path,
    command: list[str],
    *,
    env: dict[str, str],
    cwd: Path,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(binary), "--config", str(config), *command],
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        check=check,
    )


def daemon_status(
    binary: Path,
    config: Path,
    *,
    env: dict[str, str],
    cwd: Path,
) -> dict[str, Any]:
    completed = run_cli(
        binary,
        config,
        ["daemon", "status", "--json"],
        env=env,
        cwd=cwd,
    )
    payload = json.loads(completed.stdout)
    if payload.get("status") != "running" or not isinstance(
        payload.get("pid"),
        int,
    ):
        raise AssertionError("Vyane daemon status was not a running view")
    return payload


def extract_contract(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        if value.get("schema_version") == "0.1.0" and "operation_status" in value:
            return value
        for item in value.values():
            if (found := extract_contract(item)) is not None:
                return found
        return None
    if isinstance(value, list):
        for item in value:
            if (found := extract_contract(item)) is not None:
                return found
        return None
    if not isinstance(value, str):
        return None
    marker = "```json\n"
    start = value.find(marker)
    end = value.find("\n```", start + len(marker))
    candidates = (
        [value[start + len(marker) : end]] if start >= 0 and end >= 0 else [value]
    )
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and parsed.get("schema_version") == "0.1.0":
            return parsed
    return None


def console_command(
    client: httpx.Client,
    base_url: str,
    command: str,
    sequence: int,
) -> dict[str, Any]:
    submission = request(
        client,
        "POST",
        base_url,
        "/api/console/chat/task",
        json={
            "channel": "console",
            "user_id": "vyane-paw-durable",
            "session_id": f"vyane-paw-durable-{sequence}",
            "timeout": 30,
            "request_context": {"approval_level": "off"},
            "input": [
                {
                    "role": "user",
                    "type": "message",
                    "content": [{"type": "text", "text": command}],
                },
            ],
        },
    ).json()
    final = wait_for_task(client, base_url, submission["task_id"], 45)
    result = final.get("result")
    if not isinstance(result, dict) or result.get("status") != "completed":
        raise AssertionError("QwenPaw durable command did not complete")
    contract = extract_contract(result)
    if contract is None:
        raise AssertionError("QwenPaw durable command returned no result contract")
    return contract


def assert_contract(
    payload: dict[str, Any],
    *,
    tool: str,
    mode: str,
    caller_id: str | None = None,
) -> tuple[str, str]:
    if payload.get("tool") != tool or payload.get("mode") != mode:
        raise AssertionError("durable result identity drifted")
    if payload.get("operation_status") != "completed":
        raise AssertionError("durable control operation was not completed")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise AssertionError("durable result omitted lifecycle data")
    result_id = data.get("caller_id")
    state = data.get("state")
    if not isinstance(result_id, str) or not isinstance(state, str):
        raise AssertionError("durable lifecycle view was malformed")
    parsed = uuid.UUID(result_id)
    if parsed.version != 7 or str(parsed) != result_id:
        raise AssertionError("durable lifecycle id was not canonical UUIDv7")
    if caller_id is not None and result_id != caller_id:
        raise AssertionError("durable lifecycle target changed")
    return result_id, state


def assert_task_absent_from_logs(root: Path) -> None:
    marker = DURABLE_TASK.encode()
    for path in (root / "qwenpaw-app.log", root / "data" / "daemon.log"):
        if path.is_file() and marker in path.read_bytes():
            raise AssertionError("durable task entered a runtime log")


def wait_for_workflow_state(
    client: httpx.Client,
    base_url: str,
    caller_id: str,
    wanted: set[str],
    *,
    sequence: int,
    timeout: float,
) -> tuple[dict[str, Any], int]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        last = console_command(
            client,
            base_url,
            f"/vyane workflow-status {caller_id}",
            sequence,
        )
        sequence += 1
        _, state = assert_contract(
            last,
            tool="vyane_workflow_status",
            mode="workflow-status",
            caller_id=caller_id,
        )
        if state in wanted:
            return last, sequence
        time.sleep(0.1)
    raise AssertionError(f"workflow did not reach {sorted(wanted)}: {last}")


def run(args: argparse.Namespace) -> dict[str, Any]:  # noqa: PLR0915
    started_at = datetime.now(UTC)
    started = time.monotonic()
    root = args.runtime_root.resolve()
    for name in (
        "app-home",
        "backups",
        "data",
        "secret",
        "working",
        "xdg-config",
    ):
        (root / name).mkdir(parents=True, exist_ok=True)
    (root / "working" / ".telemetry_collected").touch()
    config_path = root / "vyane.toml"
    policy_path = root / "policy.json"
    mcp_wrapper = write_mcp_wrapper(root, args.launcher.resolve())
    endpoint_state = EndpointState("should-be-cancelled", delay_seconds=10)

    base_env = {
        "HOME": str(root / "app-home"),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "NO_PROXY": "*",
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "RUST_LOG": "warn",
        "VYANE_DATA_DIR": str(root / "data"),
        "XDG_CONFIG_HOME": str(root / "xdg-config"),
    }
    app_env = {
        **base_env,
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUNBUFFERED": "1",
        "QWENPAW_AUTH_ENABLED": "false",
        "QWENPAW_BACKUP_DIR": str(root / "backups"),
        "QWENPAW_RUNNING_IN_CONTAINER": "true",
        "QWENPAW_SECRET_DIR": str(root / "secret"),
        "QWENPAW_WORKING_DIR": str(root / "working"),
        "VYANE_PAW_POLICY": str(policy_path),
    }
    if SENSITIVE_ENV_NAMES.intersection(app_env):
        raise AssertionError("credential-bearing environment entered app process")

    app_process: subprocess.Popen[Any] | None = None
    app_exit_code = -1
    daemon_pid = 0
    mcp_pid = 0
    sequence = 1
    daemon_started = False
    with RunningEndpoint(endpoint_state) as endpoint:
        write_config(config_path, endpoint)
        write_policy(policy_path)
        run_cli(
            args.vyane_bin.resolve(),
            config_path,
            ["daemon", "start", "--addr", "127.0.0.1:0"],
            env=base_env,
            cwd=root / "working",
        )
        daemon_started = True
        try:
            daemon_pid = int(
                daemon_status(
                    args.vyane_bin.resolve(),
                    config_path,
                    env=base_env,
                    cwd=root / "working",
                )["pid"],
            )
        except BaseException:
            run_cli(
                args.vyane_bin.resolve(),
                config_path,
                ["daemon", "stop"],
                env=base_env,
                cwd=root / "working",
                check=False,
            )
            raise

        app_port = free_port()
        app_url = f"http://127.0.0.1:{app_port}"
        app_log_path = root / "qwenpaw-app.log"
        try:
            with app_log_path.open("wb") as app_log:
                app_process = start_app(
                    env=app_env,
                    port=app_port,
                    log=app_log,
                )
                with httpx.Client(
                    timeout=httpx.Timeout(30.0),
                    trust_env=False,
                ) as client:
                    wait_for_health(client, app_url, app_process, 60)
                    request(
                        client,
                        "POST",
                        app_url,
                        "/api/mcp",
                        json={
                            "client_key": MCP_CLIENT_KEY,
                            "client": {
                                "name": MCP_CLIENT_KEY,
                                "description": "Durable workflow integration",
                                "enabled": True,
                                "transport": "stdio",
                                "command": str(mcp_wrapper),
                                "args": [],
                                "env": {
                                    **base_env,
                                    "VYANE_PAW_CONFIG": str(config_path),
                                    "VYANE_PAW_VYANE_BIN": str(
                                        args.vyane_bin.resolve(),
                                    ),
                                },
                                "cwd": str(root / "working"),
                                "tools": DURABLE_TOOLS,
                            },
                        },
                    )
                    request(
                        client,
                        "PUT",
                        app_url,
                        f"/api/mcp/policy/{MCP_CLIENT_KEY}",
                        json={
                            "default_effect": "allow",
                            "client_overrides": [],
                            "tool_defaults": [],
                            "tool_overrides": [],
                            "unmanaged_rules_count": 0,
                        },
                    )
                    listed = wait_for_mcp_tools(client, app_url, 30)
                    enabled = sorted(
                        item["name"] for item in listed if item.get("enabled")
                    )
                    if enabled != sorted(DURABLE_TOOLS):
                        raise AssertionError("durable MCP tool surface drifted")
                    install_plugin(
                        client,
                        app_url,
                        args.plugin_dir.resolve(),
                        30,
                    )
                    initial_mcp_pid = wait_for_pid_file(
                        root / "vyane-mcp.pid",
                        10,
                    )
                    if stop_app(app_process) != 0:
                        raise AssertionError("QwenPaw install phase failed")
                    wait_for_process_exit(initial_mcp_pid, 10)
                    (root / "vyane-mcp.pid").unlink(missing_ok=True)

                    app_process = start_app(
                        env=app_env,
                        port=app_port,
                        log=app_log,
                    )
                    wait_for_health(client, app_url, app_process, 60)
                    listed = wait_for_mcp_tools(client, app_url, 30)
                    enabled = sorted(
                        item["name"] for item in listed if item.get("enabled")
                    )
                    if enabled != sorted(DURABLE_TOOLS):
                        raise AssertionError(
                            "durable tools drifted after app restart",
                        )
                    wait_for_plugin_command(client, app_url, 30)

                    submitted = console_command(
                        client,
                        app_url,
                        f"/vyane workflow-submit slow -- {DURABLE_TASK}",
                        sequence,
                    )
                    sequence += 1
                    caller_id, submitted_state = assert_contract(
                        submitted,
                        tool="vyane_workflow_submit",
                        mode="workflow-submit",
                    )
                    if submitted_state not in {"queued", "running"}:
                        raise AssertionError("workflow submit was not accepted")

                    _, sequence = wait_for_workflow_state(
                        client,
                        app_url,
                        caller_id,
                        {"running"},
                        sequence=sequence,
                        timeout=10,
                    )
                    first_cancel = console_command(
                        client,
                        app_url,
                        f"/vyane workflow-cancel {caller_id}",
                        sequence,
                    )
                    sequence += 1
                    _, first_cancel_state = assert_contract(
                        first_cancel,
                        tool="vyane_workflow_cancel",
                        mode="workflow-cancel",
                        caller_id=caller_id,
                    )
                    if first_cancel_state not in {"cancelling", "cancelled"}:
                        raise AssertionError("workflow cancellation was not accepted")

                    repeated_cancel = console_command(
                        client,
                        app_url,
                        f"/vyane workflow-cancel {caller_id}",
                        sequence,
                    )
                    sequence += 1
                    _, repeated_cancel_state = assert_contract(
                        repeated_cancel,
                        tool="vyane_workflow_cancel",
                        mode="workflow-cancel",
                        caller_id=caller_id,
                    )
                    if repeated_cancel_state not in {
                        "cancelling",
                        "cancelled",
                    }:
                        raise AssertionError("repeated cancellation was not idempotent")

                    terminal, sequence = wait_for_workflow_state(
                        client,
                        app_url,
                        caller_id,
                        {"cancelled"},
                        sequence=sequence,
                        timeout=10,
                    )
                    _, terminal_state = assert_contract(
                        terminal,
                        tool="vyane_workflow_status",
                        mode="workflow-status",
                        caller_id=caller_id,
                    )
                    if terminal_state != "cancelled":
                        raise AssertionError("workflow cancellation was not terminal")
                    if endpoint_state.requests < 1:
                        raise AssertionError(
                            "workflow never reached the synthetic provider",
                        )
                    mcp_pid = wait_for_pid_file(root / "vyane-mcp.pid", 10)
            app_exit_code = stop_app(app_process)
        finally:
            if app_process is not None and app_process.poll() is None:
                app_exit_code = stop_app(app_process)
            if daemon_started:
                stopped = run_cli(
                    args.vyane_bin.resolve(),
                    config_path,
                    ["daemon", "stop"],
                    env=base_env,
                    cwd=root / "working",
                    check=False,
                )
                if stopped.returncode != 0:
                    raise AssertionError(
                        f"Vyane daemon stop failed: {stopped.stderr.strip()}",
                    )

    if app_exit_code != 0:
        raise AssertionError(f"QwenPaw app exited with {app_exit_code}")
    if mcp_pid <= 0 or daemon_pid <= 0:
        raise AssertionError("integration process identity was not captured")
    wait_for_process_exit(mcp_pid, 10)
    wait_for_process_exit(daemon_pid, 10)
    assert_task_absent_from_logs(root)
    lock = json.loads(args.upstreams_lock.read_text(encoding="utf-8"))
    upstreams = lock["upstreams"]
    return {
        "schema_version": "0.1.0",
        "scenario": "durable_workflow",
        "sanitization_state": "sanitized",
        "started_at": started_at.isoformat(),
        "duration_ms": round((time.monotonic() - started) * 1000),
        "upstream_revisions": {
            "qwenpaw": upstreams["qwenpaw"]["revision"],
            "vyane_rs": args.vyane_revision,
            "rmcp": args.rmcp_version,
        },
        "result": "passed",
        "metrics": {
            "app_exit_code": app_exit_code,
            "app_process_reaped": 1,
            "daemon_process_reaped": 1,
            "mcp_process_reaped": 1,
            "provider_requests": endpoint_state.requests,
            "repeated_cancel_requests": 2,
            "task_log_leaks": 0,
            "terminal_cancelled": 1,
            "workflow_submitted": 1,
        },
        "limitations": [
            "fixed single-step read-only workflow only",
            "custom Vyane workflow tools, not the MCP Tasks extension",
            "loopback daemon and synthetic provider only",
            "no model selected workflow arguments",
        ],
    }


def main() -> None:
    args = parse_args()
    evidence = run(args)
    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    args.evidence.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(evidence, ensure_ascii=False))


if __name__ == "__main__":
    main()
