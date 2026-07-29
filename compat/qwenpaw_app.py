#!/usr/bin/env python3
"""Headless integration through the real pinned QwenPaw application."""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import stat
import subprocess
import threading
import time
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import httpx


MCP_CLIENT_KEY = "vyane-paw"
EXPOSED_ROUTE_TOOL = "vyane-paw__vyane_route"
RAW_PRODUCT_TOOLS = ["vyane_broadcast", "vyane_dispatch", "vyane_route"]
SENSITIVE_ENV_NAMES = {
    "ANTHROPIC_API_KEY",
    "DASHSCOPE_API_KEY",
    "DISCORD_TOKEN",
    "GITHUB_TOKEN",
    "OPENAI_API_KEY",
    "TELEGRAM_BOT_TOKEN",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plugin-dir", type=Path, required=True)
    parser.add_argument("--launcher", type=Path, required=True)
    parser.add_argument("--vyane-bin", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--upstreams-lock", type=Path, required=True)
    parser.add_argument("--rmcp-version", required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    return parser.parse_args()


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class ModelState:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.tool_results: list[str] = []
        self.lock = threading.Lock()


class SyntheticModelHandler(BaseHTTPRequestHandler):
    server: "SyntheticModelServer"

    def do_GET(self) -> None:  # noqa: N802
        if not self.path.endswith("/models"):
            self.send_error(404)
            return
        self._json_response(
            {
                "object": "list",
                "data": [{"id": "vyane-paw-synthetic", "object": "model"}],
            },
        )

    def do_POST(self) -> None:  # noqa: N802
        if not self.path.endswith("/chat/completions"):
            self.send_error(404)
            return
        body = self._read_json()
        with self.server.state.lock:
            self.server.state.requests.append(body)
        messages = body.get("messages") if isinstance(body, dict) else None
        messages = messages if isinstance(messages, list) else []
        tools = body.get("tools") if isinstance(body, dict) else None
        tools = tools if isinstance(tools, list) else []
        tool_messages = [
            message
            for message in messages
            if isinstance(message, dict) and message.get("role") == "tool"
        ]
        if tools and not tool_messages:
            self._stream_tool_call()
            return
        if tool_messages:
            content = str(tool_messages[-1].get("content", ""))
            with self.server.state.lock:
                self.server.state.tool_results.append(content)
            self._stream_text("Vyane route result received.")
            return
        self._stream_text("Synthetic title.")

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw)
        except (UnicodeError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _json_response(self, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _write_sse(self, payload: dict[str, Any]) -> None:
        self.wfile.write(f"data: {json.dumps(payload)}\n\n".encode())
        self.wfile.flush()

    def _start_sse(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

    def _stream_tool_call(self) -> None:
        self._start_sse()
        self._write_sse(
            {
                "id": "chatcmpl-vyane-paw-tool",
                "object": "chat.completion.chunk",
                "created": 1_700_000_000,
                "model": "vyane-paw-synthetic",
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "call_vyane_route",
                                    "type": "function",
                                    "function": {
                                        "name": EXPOSED_ROUTE_TOOL,
                                        "arguments": "",
                                    },
                                },
                            ],
                        },
                        "finish_reason": None,
                    },
                ],
            },
        )
        self._write_sse(
            {
                "id": "chatcmpl-vyane-paw-tool",
                "object": "chat.completion.chunk",
                "created": 1_700_000_000,
                "model": "vyane-paw-synthetic",
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "function": {
                                        "arguments": json.dumps(
                                            {
                                                "task": "synthetic docs request",
                                                "allow_frontier": False,
                                            },
                                        ),
                                    },
                                },
                            ],
                        },
                        "finish_reason": None,
                    },
                ],
            },
        )
        self._write_sse(
            {
                "id": "chatcmpl-vyane-paw-tool",
                "object": "chat.completion.chunk",
                "created": 1_700_000_000,
                "model": "vyane-paw-synthetic",
                "choices": [
                    {
                        "index": 0,
                        "delta": {},
                        "finish_reason": "tool_calls",
                    },
                ],
            },
        )
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()

    def _stream_text(self, text: str) -> None:
        self._start_sse()
        self._write_sse(
            {
                "id": "chatcmpl-vyane-paw-text",
                "object": "chat.completion.chunk",
                "created": 1_700_000_000,
                "model": "vyane-paw-synthetic",
                "choices": [
                    {
                        "index": 0,
                        "delta": {"role": "assistant", "content": text},
                        "finish_reason": None,
                    },
                ],
            },
        )
        self._write_sse(
            {
                "id": "chatcmpl-vyane-paw-text",
                "object": "chat.completion.chunk",
                "created": 1_700_000_000,
                "model": "vyane-paw-synthetic",
                "choices": [
                    {
                        "index": 0,
                        "delta": {},
                        "finish_reason": "stop",
                    },
                ],
            },
        )
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()

    def log_message(self, _format: str, *_args: Any) -> None:
        return


class SyntheticModelServer(ThreadingHTTPServer):
    state: ModelState


def request(
    client: httpx.Client,
    method: str,
    base_url: str,
    path: str,
    **kwargs: Any,
) -> httpx.Response:
    response = client.request(method, f"{base_url}{path}", **kwargs)
    if response.status_code >= 400:
        raise AssertionError(
            f"{method} {path} returned {response.status_code}: {response.text[:500]}",
        )
    return response


def wait_for_health(
    client: httpx.Client,
    base_url: str,
    process: subprocess.Popen[Any],
    timeout: float,
) -> None:
    deadline = time.monotonic() + timeout
    last_error = ""
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise AssertionError(
                f"QwenPaw app exited during startup with {process.returncode}",
            )
        try:
            response = client.get(f"{base_url}/api/healthz")
            if response.status_code == 200:
                return
            last_error = f"HTTP {response.status_code}"
        except httpx.HTTPError as exc:
            last_error = type(exc).__name__
        time.sleep(0.25)
    raise AssertionError(f"QwenPaw app did not become healthy: {last_error}")


def start_app(
    *,
    env: dict[str, str],
    port: int,
    log: Any,
) -> subprocess.Popen[Any]:
    return subprocess.Popen(
        [
            os.sys.executable,
            "-m",
            "qwenpaw",
            "app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "info",
        ],
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=subprocess.STDOUT,
    )


def stop_app(process: subprocess.Popen[Any], timeout: float = 20) -> int:
    if process.poll() is None:
        process.send_signal(signal.SIGINT)
    try:
        return process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            return process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            return process.wait(timeout=5)


def install_plugin(
    client: httpx.Client,
    base_url: str,
    plugin_dir: Path,
    timeout: float,
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.post(
            f"{base_url}/api/plugins/install",
            json={"source": str(plugin_dir), "force": True},
        )
        if response.status_code == 200:
            payload = response.json()
            if payload.get("id") != MCP_CLIENT_KEY:
                raise AssertionError("QwenPaw loaded an unexpected plugin")
            return
        if response.status_code != 503:
            raise AssertionError(
                f"plugin install failed with {response.status_code}: "
                f"{response.text[:500]}",
            )
        time.sleep(0.25)
    raise AssertionError("QwenPaw plugin loader did not become ready")


def wait_for_plugin_command(
    client: httpx.Client,
    base_url: str,
    timeout: float,
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"{base_url}/api/workspace/commands/available")
        if response.status_code == 200:
            payload = response.json()
            commands = payload.get("commands") if isinstance(payload, dict) else None
            names = {
                item.get("name") for item in commands or [] if isinstance(item, dict)
            }
            if "vyane" in names:
                return
        time.sleep(0.25)
    raise AssertionError("Vyane plugin command did not enter the live workspace")


def wait_for_task(
    client: httpx.Client,
    base_url: str,
    task_id: str,
    timeout: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        payload = request(
            client,
            "GET",
            base_url,
            f"/api/console/chat/task/{task_id}",
        ).json()
        if payload.get("status") == "finished":
            return payload
        time.sleep(0.25)
    raise AssertionError("QwenPaw console task did not finish")


def wait_for_mcp_tools(
    client: httpx.Client,
    base_url: str,
    timeout: float,
) -> list[dict[str, Any]]:
    deadline = time.monotonic() + timeout
    last_detail = ""
    while time.monotonic() < deadline:
        response = client.get(
            f"{base_url}/api/mcp/tools/{MCP_CLIENT_KEY}",
        )
        if response.status_code == 200:
            payload = response.json()
            if isinstance(payload, list):
                return payload
            raise AssertionError("QwenPaw MCP tool list was not an array")
        if response.status_code != 502:
            raise AssertionError(
                f"MCP tool listing failed with {response.status_code}: "
                f"{response.text[:500]}",
            )
        last_detail = response.text[:500]
        time.sleep(0.25)
    raise AssertionError(f"QwenPaw MCP driver did not become active: {last_detail}")


def tool_names(payload: dict[str, Any]) -> list[str]:
    names: list[str] = []
    tools = payload.get("tools")
    if not isinstance(tools, list):
        return names
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        function = tool.get("function")
        if isinstance(function, dict) and isinstance(function.get("name"), str):
            names.append(function["name"])
    return names


def request_summary(payload: dict[str, Any]) -> dict[str, Any]:
    messages = payload.get("messages")
    messages = messages if isinstance(messages, list) else []
    serialized = json.dumps(messages, ensure_ascii=False, default=str)
    user_texts = [
        str(message.get("content", ""))
        for message in messages
        if isinstance(message, dict) and message.get("role") == "user"
    ]
    return {
        "has_vyane_contract": "Vyane Paw command contract" in serialized,
        "last_user": user_texts[-1][:160] if user_texts else "",
        "tools": tool_names(payload),
    }


def process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def write_vyane_fixture(root: Path, launcher: Path) -> tuple[Path, Path]:
    config_path = root / "vyane.toml"
    config_path.write_text(
        """
[providers.synthetic]
base_url = "http://127.0.0.1:9"
auth_style = "bearer"
protocol = "openai_chat"
default_model = "synthetic-model"

[profiles.economy]
provider = "synthetic"
protocol = "openai_chat"
harness = "none"
model = "synthetic-model"
tier = "economy"
tags = ["docs"]
""".strip()
        + "\n",
        encoding="utf-8",
    )
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
    return config_path, wrapper


def run(args: argparse.Namespace) -> dict[str, Any]:
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
    config_path, mcp_wrapper = write_vyane_fixture(root, args.launcher.resolve())

    model_state = ModelState()
    model_server = SyntheticModelServer(
        ("127.0.0.1", 0),
        SyntheticModelHandler,
    )
    model_server.state = model_state
    model_thread = threading.Thread(target=model_server.serve_forever, daemon=True)
    model_thread.start()
    model_host, model_port = model_server.server_address
    model_url = f"http://{model_host}:{model_port}/v1"

    app_port = free_port()
    app_url = f"http://127.0.0.1:{app_port}"
    app_log_path = root / "qwenpaw-app.log"
    app_env = {
        "HOME": str(root / "app-home"),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "NO_PROXY": "*",
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUNBUFFERED": "1",
        "QWENPAW_AUTH_ENABLED": "false",
        "QWENPAW_BACKUP_DIR": str(root / "backups"),
        "QWENPAW_RUNNING_IN_CONTAINER": "true",
        "QWENPAW_SECRET_DIR": str(root / "secret"),
        "QWENPAW_WORKING_DIR": str(root / "working"),
    }
    if SENSITIVE_ENV_NAMES.intersection(app_env):
        raise AssertionError("credential-bearing environment entered app process")

    app_process: subprocess.Popen[Any] | None = None
    app_exit_code = -1
    mcp_pid = 0
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
                            "description": "Synthetic Vyane Paw integration",
                            "enabled": True,
                            "transport": "stdio",
                            "command": str(mcp_wrapper),
                            "args": [],
                            "env": {
                                "HOME": str(root / "app-home"),
                                "LANG": "C.UTF-8",
                                "LC_ALL": "C.UTF-8",
                                "RUST_LOG": "warn",
                                "VYANE_DATA_DIR": str(root / "data"),
                                "VYANE_PAW_CONFIG": str(config_path),
                                "VYANE_PAW_VYANE_BIN": str(
                                    args.vyane_bin.resolve(),
                                ),
                                "XDG_CONFIG_HOME": str(root / "xdg-config"),
                            },
                            "cwd": str(root / "working"),
                            "tools": RAW_PRODUCT_TOOLS,
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
                provider_id = "vyane-paw-synthetic"
                request(
                    client,
                    "POST",
                    app_url,
                    "/api/models/custom-providers",
                    json={
                        "id": provider_id,
                        "name": "Vyane Paw Synthetic",
                        "default_base_url": model_url,
                        "chat_model": "OpenAIChatModel",
                        "models": [
                            {
                                "id": "vyane-paw-synthetic",
                                "name": "Vyane Paw Synthetic",
                            },
                        ],
                    },
                )
                request(
                    client,
                    "PUT",
                    app_url,
                    f"/api/models/{provider_id}/config",
                    json={"api_key": "synthetic-key", "base_url": model_url},
                )
                request(
                    client,
                    "PUT",
                    app_url,
                    "/api/models/active",
                    json={
                        "provider_id": provider_id,
                        "model": "vyane-paw-synthetic",
                        "scope": "global",
                    },
                )
                listed_tools = wait_for_mcp_tools(client, app_url, 30)
                enabled_tools = sorted(
                    item["name"] for item in listed_tools if item.get("enabled")
                )
                if enabled_tools != RAW_PRODUCT_TOOLS:
                    raise AssertionError(
                        "MCP tools drifted after provider-triggered reload",
                    )
                install_plugin(client, app_url, args.plugin_dir.resolve(), 30)
                initial_exit_code = stop_app(app_process)
                if initial_exit_code != 0:
                    raise AssertionError(
                        f"QwenPaw installation phase exited with {initial_exit_code}",
                    )
                app_process = start_app(
                    env=app_env,
                    port=app_port,
                    log=app_log,
                )
                wait_for_health(client, app_url, app_process, 60)
                listed_tools = wait_for_mcp_tools(client, app_url, 30)
                enabled_tools = sorted(
                    item["name"] for item in listed_tools if item.get("enabled")
                )
                if enabled_tools != RAW_PRODUCT_TOOLS:
                    raise AssertionError(
                        "MCP tools drifted after installed-plugin restart",
                    )
                wait_for_plugin_command(client, app_url, 30)
                submission = request(
                    client,
                    "POST",
                    app_url,
                    "/api/console/chat/task",
                    json={
                        "channel": "console",
                        "user_id": "vyane-paw-headless",
                        "session_id": "vyane-paw-headless",
                        "timeout": 45,
                        "request_context": {"approval_level": "off"},
                        "input": [
                            {
                                "role": "user",
                                "type": "message",
                                "content": [
                                    {
                                        "type": "text",
                                        "text": ("/vyane route synthetic docs request"),
                                    },
                                ],
                            },
                        ],
                    },
                ).json()
                final = wait_for_task(
                    client,
                    app_url,
                    submission["task_id"],
                    60,
                )
                result = final.get("result")
                if not isinstance(result, dict) or result.get("status") != "completed":
                    raise AssertionError(f"QwenPaw task failed: {final}")

                with model_state.lock:
                    requests = list(model_state.requests)
                    tool_results = list(model_state.tool_results)
                visible_surfaces = [
                    names for payload in requests if (names := tool_names(payload))
                ]
                if not visible_surfaces or any(
                    surface != [EXPOSED_ROUTE_TOOL] for surface in visible_surfaces
                ):
                    raise AssertionError(
                        "unexpected model-visible tool surfaces: "
                        + json.dumps(
                            [request_summary(payload) for payload in requests],
                            ensure_ascii=False,
                        ),
                    )
                if len(tool_results) != 1:
                    raise AssertionError(
                        f"expected one Vyane tool result, got {len(tool_results)}",
                    )
                try:
                    normalized = json.loads(tool_results[0])
                except json.JSONDecodeError as exc:
                    raise AssertionError("tool result was not structured JSON") from exc
                expected_contract = {
                    "schema_version": "0.1.0",
                    "tool": "vyane_route",
                    "mode": "route",
                    "policy_profile": "local-safe",
                    "operation_status": "completed",
                    "outcome": "success",
                    "detail_state": "full",
                    "retry_guidance": "do_not_retry",
                }
                for key, value in expected_contract.items():
                    if normalized.get(key) != value:
                        raise AssertionError(
                            f"normalized result field {key} was unexpected",
                        )
                data = normalized.get("data")
                if not isinstance(data, dict) or data.get("profile") != "economy":
                    raise AssertionError("route decision was not preserved")
                serialized = json.dumps(normalized, ensure_ascii=False)
                forbidden = [
                    str(root),
                    str(args.plugin_dir.resolve()),
                    str(args.vyane_bin.resolve()),
                    model_url,
                    "synthetic-key",
                ]
                if any(marker in serialized for marker in forbidden):
                    raise AssertionError(
                        "normalized result leaked private runtime data"
                    )

                pid_path = root / "vyane-mcp.pid"
                deadline = time.monotonic() + 10
                while not pid_path.is_file() and time.monotonic() < deadline:
                    time.sleep(0.05)
                if not pid_path.is_file():
                    raise AssertionError("Vyane MCP process was not observed")
                mcp_pid = int(pid_path.read_text(encoding="utf-8").strip())
        app_exit_code = stop_app(app_process)
    finally:
        if app_process is not None and app_process.poll() is None:
            app_exit_code = stop_app(app_process)
        model_server.shutdown()
        model_server.server_close()
        model_thread.join(timeout=5)

    if app_exit_code != 0:
        raise AssertionError(f"QwenPaw app exited with {app_exit_code}")
    if mcp_pid <= 0 or process_alive(mcp_pid):
        raise AssertionError("Vyane MCP process was not reaped")
    lock = json.loads(args.upstreams_lock.read_text(encoding="utf-8"))
    upstreams = lock["upstreams"]
    return {
        "schema_version": "0.1.0",
        "scenario": "qwenpaw_application",
        "sanitization_state": "sanitized",
        "started_at": started_at.isoformat(),
        "duration_ms": round((time.monotonic() - started) * 1000),
        "upstream_revisions": {
            "qwenpaw": upstreams["qwenpaw"]["revision"],
            "vyane_rs": upstreams["vyane_rs"]["revision"],
            "rmcp": args.rmcp_version,
        },
        "result": "passed",
        "metrics": {
            "app_exit_code": app_exit_code,
            "app_process_reaped": 1,
            "mcp_process_reaped": 1,
            "model_visible_tools": 1,
            "normalized_results": 1,
            "operator_interventions": 0,
        },
        "limitations": [
            "headless local FastAPI application only",
            "synthetic OpenAI-compatible model, not a semantic quality test",
            "route mode only; no target execution",
        ],
    }


def main() -> None:
    args = parse_args()
    evidence = run(args)
    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    args.evidence.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(evidence, ensure_ascii=False))


if __name__ == "__main__":
    main()
