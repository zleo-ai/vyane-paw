#!/usr/bin/env python3
"""Hermetic VP-02 product-flow tests through the pinned QwenPaw MCP client."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import tempfile
import threading
import time
from contextlib import ExitStack
from dataclasses import dataclass, field
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from smoke import (
    load_qwenpaw_client,
    result_payload,
    revision_map,
    wait_for_file,
    write_server_launcher,
)


SYNTHETIC_TASK = "Compare two synthetic implementation options."


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qwenpaw-client", type=Path, required=True)
    parser.add_argument("--vyane-bin", type=Path, required=True)
    parser.add_argument("--rmcp-version", required=True)
    parser.add_argument("--upstreams-lock", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    return parser.parse_args()


@dataclass
class ConcurrencyTracker:
    active: int = 0
    maximum: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)

    def enter(self) -> None:
        with self.lock:
            self.active += 1
            self.maximum = max(self.maximum, self.active)

    def leave(self) -> None:
        with self.lock:
            self.active -= 1


@dataclass
class EndpointState:
    answer: str
    status: int = 200
    delay_seconds: float = 0
    requests: int = 0
    tracker: ConcurrencyTracker | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)

    def count_request(self) -> None:
        with self.lock:
            self.requests += 1


class DemoHttpServer(ThreadingHTTPServer):
    state: EndpointState


class DemoHandler(BaseHTTPRequestHandler):
    server: DemoHttpServer

    def do_POST(self) -> None:  # noqa: N802
        state = self.server.state
        state.count_request()
        content_length = int(self.headers.get("content-length", "0"))
        body = self.rfile.read(content_length)
        try:
            request = json.loads(body)
        except json.JSONDecodeError:
            self.send_error(400)
            return
        if self.path != "/v1/chat/completions" or not request.get("model"):
            self.send_error(404)
            return

        tracker = state.tracker
        if tracker is not None:
            tracker.enter()
        try:
            if state.delay_seconds:
                time.sleep(state.delay_seconds)
            if state.status != 200:
                response = {"error": {"message": "synthetic failure"}}
            else:
                response = {
                    "id": "synthetic-response",
                    "model": request["model"],
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": state.answer,
                            },
                            "finish_reason": "stop",
                        },
                    ],
                    "usage": {
                        "prompt_tokens": 5,
                        "completion_tokens": 3,
                    },
                }
            encoded = json.dumps(response).encode()
            self.send_response(state.status)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(encoded)))
            self.end_headers()
            try:
                self.wfile.write(encoded)
            except (BrokenPipeError, ConnectionResetError):
                pass
        finally:
            if tracker is not None:
                tracker.leave()

    def log_message(self, _format: str, *_args: Any) -> None:
        return


class RunningEndpoint:
    def __init__(self, state: EndpointState) -> None:
        self.state = state
        self.server = DemoHttpServer(("127.0.0.1", 0), DemoHandler)
        self.server.state = state
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            daemon=True,
        )

    @property
    def url(self) -> str:
        host, port = self.server.server_address
        return f"http://{host}:{port}"

    def __enter__(self) -> RunningEndpoint:
        self.thread.start()
        return self

    def __exit__(self, *_args: Any) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


def provider(name: str, endpoint: RunningEndpoint) -> str:
    return f"""
[providers.{name}]
base_url = "{endpoint.url}"
auth_style = "bearer"
protocol = "openai_chat"
default_model = "synthetic-model"
"""


def profile(
    name: str,
    provider_name: str,
    *,
    extra: str = "",
) -> str:
    return f"""
[profiles.{name}]
provider = "{provider_name}"
protocol = "openai_chat"
harness = "none"
model = "synthetic-model"
{extra}
"""


def write_demo_config(
    path: Path,
    endpoints: dict[str, RunningEndpoint],
) -> None:
    config = "".join(provider(name, endpoint) for name, endpoint in endpoints.items())
    config += profile(
        "economy",
        "route",
        extra='tier = "economy"\ntags = ["docs"]',
    )
    config += profile(
        "reviewer",
        "route",
        extra='tier = "mainline"\nstage = "review"',
    )
    config += profile(
        "resilient",
        "primary",
        extra='tier = "mainline"\nfailover = ["backup"]',
    )
    config += profile("backup", "backup", extra='tier = "economy"')
    config += profile("review-a", "review_a")
    config += profile("review-b", "review_b")
    config += profile("hard-fail", "hard_fail")
    config += profile("slow", "slow")
    path.write_text(config, encoding="utf-8")


def assert_output(payload: dict[str, Any], expected: str) -> None:
    if payload.get("operation_status") != "completed":
        raise AssertionError("operation did not complete")
    if payload.get("output") != expected:
        raise AssertionError("operation returned an unexpected output")
    if payload.get("record", {}).get("status") != "success":
        raise AssertionError("operation did not record success")


async def wait_for_history(
    client: Any,
    status: str,
    *,
    timeout: float = 5,
) -> list[dict[str, Any]]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        payload = result_payload(
            await client.call_tool(
                "vyane_history",
                {"limit": 20, "status": status},
            ),
        )
        items = payload.get("items", [])
        if items:
            return items
        await asyncio.sleep(0.05)
    raise AssertionError(f"no {status} run appeared in history")


async def history_count(client: Any, status: str) -> int:
    payload = result_payload(
        await client.call_tool(
            "vyane_history",
            {"limit": 20, "status": status},
        ),
    )
    return len(payload.get("items", []))


async def wait_for_history_growth(
    client: Any,
    status: str,
    previous: int,
    *,
    timeout: float = 7,
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if await history_count(client, status) > previous:
            return
        await asyncio.sleep(0.05)
    raise AssertionError(f"{status} history did not grow")


def evidence(
    args: argparse.Namespace,
    scenario: str,
    started_at: datetime,
    started: float,
    metrics: dict[str, int],
    limitations: list[str],
) -> dict[str, Any]:
    return {
        "schema_version": "0.1.0",
        "scenario": scenario,
        "sanitization_state": "sanitized",
        "started_at": started_at.isoformat(),
        "duration_ms": round((time.monotonic() - started) * 1000),
        "upstream_revisions": revision_map(
            args.upstreams_lock,
            args.rmcp_version,
        ),
        "result": "passed",
        "metrics": metrics,
        "limitations": limitations,
    }


async def run_flows(args: argparse.Namespace) -> list[dict[str, Any]]:
    client_type = load_qwenpaw_client(args.qwenpaw_client)
    review_tracker = ConcurrencyTracker()
    states = {
        "route": EndpointState("route-answer"),
        "primary": EndpointState("", status=500),
        "backup": EndpointState("fallback-answer"),
        "review_a": EndpointState(
            "review-a",
            delay_seconds=0.25,
            tracker=review_tracker,
        ),
        "review_b": EndpointState(
            "review-b",
            delay_seconds=0.25,
            tracker=review_tracker,
        ),
        "hard_fail": EndpointState("", status=500),
        "slow": EndpointState("too-late", delay_seconds=5),
    }

    with ExitStack() as stack:
        endpoints = {
            name: stack.enter_context(RunningEndpoint(state))
            for name, state in states.items()
        }
        with tempfile.TemporaryDirectory(
            prefix="vyane-paw-vp02-",
        ) as temp:
            root = Path(temp)
            for name in ("home", "config", "data", "work"):
                (root / name).mkdir()
            config_path = root / "config.toml"
            write_demo_config(config_path, endpoints)
            launcher, pid_file, exit_status_file = write_server_launcher(root)
            child_env = {
                "HOME": str(root / "home"),
                "LANG": "C.UTF-8",
                "LC_ALL": "C.UTF-8",
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                "RUST_LOG": "warn",
                "VYANE_PAW_SERVER_BIN": str(args.vyane_bin),
                "VYANE_PAW_SERVER_EXIT_FILE": str(exit_status_file),
                "VYANE_PAW_SERVER_PID_FILE": str(pid_file),
                "VYANE_DATA_DIR": str(root / "data"),
                "XDG_CONFIG_HOME": str(root / "config"),
            }
            client = client_type(
                name="vyane-paw-vp02",
                command=str(launcher),
                args=["--config", str(config_path), "mcp"],
                env=child_env,
                cwd=str(root / "work"),
                read_timeout_seconds=15,
            )
            documents: list[dict[str, Any]] = []
            try:
                await client.connect(timeout=30)

                route_started_at = datetime.now(UTC)
                route_started = time.monotonic()
                route = result_payload(
                    await client.call_tool(
                        "vyane_route",
                        {
                            "task": SYNTHETIC_TASK,
                            "stage": "review",
                            "candidates": ["economy", "reviewer"],
                        },
                    ),
                )
                if route.get("profile") != "reviewer":
                    raise AssertionError("review stage selected wrong profile")
                if SYNTHETIC_TASK in json.dumps(route):
                    raise AssertionError("route result echoed the task")
                documents.append(
                    evidence(
                        args,
                        "route",
                        route_started_at,
                        route_started,
                        {
                            "routing_decision_valid": 1,
                            "operator_interventions": 0,
                        },
                        ["deterministic synthetic routing fixture"],
                    ),
                )

                failover_started_at = datetime.now(UTC)
                failover_started = time.monotonic()
                dispatch = result_payload(
                    await client.call_tool(
                        "vyane_dispatch",
                        {
                            "task": SYNTHETIC_TASK,
                            "target": "resilient",
                            "timeout_secs": 5,
                        },
                    ),
                )
                fallback_recovery_latency_ms = round(
                    (time.monotonic() - failover_started) * 1000,
                )
                assert_output(dispatch, "fallback-answer")
                attempts = dispatch["record"]["attempts"]
                if len(attempts) != 2:
                    raise AssertionError("failover did not record two attempts")
                if not attempts[0]["outcome"].get("failed_over"):
                    raise AssertionError("primary failure was not marked failed over")
                primary_attempts = states["primary"].requests
                fallback_attempts = states["backup"].requests
                duplicate_side_effects = max(0, fallback_attempts - 1)
                if primary_attempts < 1 or fallback_attempts != 1:
                    raise AssertionError(
                        "failover endpoint request counts were unexpected",
                    )

                isolation = result_payload(
                    await client.call_tool(
                        "vyane_broadcast",
                        {
                            "task": SYNTHETIC_TASK,
                            "targets": "hard-fail,review-a",
                            "timeout_secs": 5,
                        },
                    ),
                )
                isolation_items = isolation.get("items", [])
                isolated_successes = sum(
                    item.get("record", {}).get("status") == "success"
                    for item in isolation_items
                )
                isolated_failures = sum(
                    item.get("error") is not None
                    or item.get("record", {}).get("status") == "error"
                    for item in isolation_items
                )
                if (isolated_successes, isolated_failures) != (1, 1):
                    statuses = [
                        {
                            "target": item.get("target"),
                            "record_status": item.get("record", {}).get(
                                "status",
                            ),
                            "error_code": item.get("error", {}).get("code"),
                        }
                        for item in isolation_items
                    ]
                    raise AssertionError(
                        f"unexpected isolation statuses: {statuses!r}",
                    )

                timeout_started = time.monotonic()
                timed_out = result_payload(
                    await client.call_tool(
                        "vyane_dispatch",
                        {
                            "task": SYNTHETIC_TASK,
                            "target": "slow",
                            "timeout_secs": 1,
                        },
                    ),
                )
                timeout_duration_ms = round(
                    (time.monotonic() - timeout_started) * 1000,
                )
                timeout_recorded = (
                    timed_out.get("record", {}).get("status") == "timeout"
                )
                timeout_error = timed_out.get("error", {}).get("code")
                if not timeout_recorded and timeout_error is None:
                    projection = {
                        "operation_status": timed_out.get("operation_status"),
                        "record_status": timed_out.get("record", {}).get(
                            "status",
                        ),
                        "error_code": timeout_error,
                    }
                    raise AssertionError(
                        f"unexpected timeout result: {projection!r}",
                    )
                await wait_for_history(client, "timeout")

                successes_before_cancel = await history_count(
                    client,
                    "success",
                )
                cancel_task = asyncio.create_task(
                    client.call_tool(
                        "vyane_dispatch",
                        {
                            "task": SYNTHETIC_TASK,
                            "target": "slow",
                        },
                    ),
                )
                cancel_deadline = time.monotonic() + 2
                prior_requests = states["slow"].requests
                while states["slow"].requests == prior_requests:
                    if time.monotonic() >= cancel_deadline:
                        raise AssertionError("cancel fixture did not start")
                    await asyncio.sleep(0.02)
                cancel_task.cancel()
                try:
                    await cancel_task
                except asyncio.CancelledError:
                    pass
                else:
                    raise AssertionError("cancelled call returned normally")
                await wait_for_history_growth(
                    client,
                    "success",
                    successes_before_cancel,
                )
                cancelled_runs = await history_count(client, "cancelled")

                documents.append(
                    evidence(
                        args,
                        "failover",
                        failover_started_at,
                        failover_started,
                        {
                            "fallback_success": 1,
                            "fallback_recovery_latency_ms": (
                                fallback_recovery_latency_ms
                            ),
                            "primary_attempts": primary_attempts,
                            "fallback_attempts": fallback_attempts,
                            "duplicate_side_effects": duplicate_side_effects,
                            "isolated_successes": isolated_successes,
                            "isolated_failures": isolated_failures,
                            "timeout_bounded": int(timeout_duration_ms < 2500),
                            "cancellation_probe_completed": 1,
                            "cancellation_propagated": int(
                                cancelled_runs > 0,
                            ),
                        },
                        [
                            "synthetic HTTP failures only",
                            "side effects represented by request counts",
                            (
                                "pinned QwenPaw coroutine cancellation does "
                                "not propagate an MCP cancellation notification"
                            ),
                        ],
                    ),
                )

                broadcast_started_at = datetime.now(UTC)
                broadcast_started = time.monotonic()
                broadcast = result_payload(
                    await client.call_tool(
                        "vyane_broadcast",
                        {
                            "task": SYNTHETIC_TASK,
                            "targets": "review-a,review-b",
                            "timeout_secs": 5,
                        },
                    ),
                )
                items = broadcast.get("items", [])
                outputs = {item.get("output") for item in items}
                if outputs != {"review-a", "review-b"}:
                    raise AssertionError("broadcast outputs were incomplete")
                if review_tracker.maximum < 2:
                    raise AssertionError("broadcast targets did not overlap")
                documents.append(
                    evidence(
                        args,
                        "broadcast",
                        broadcast_started_at,
                        broadcast_started,
                        {
                            "independent_valid_responses": 2,
                            "max_observed_concurrency": review_tracker.maximum,
                            "operator_interventions": 0,
                        },
                        [
                            "synthetic responses, not semantic model review",
                            "cost proxy omitted because no paid model was called",
                        ],
                    ),
                )
            finally:
                await client.close(ignore_errors=False)

            if client.is_connected or client._lifecycle_task is not None:
                raise AssertionError("QwenPaw client lifecycle did not close")
            await wait_for_file(exit_status_file, timeout=5)
            if exit_status_file.read_text(encoding="utf-8").strip() != "0":
                raise AssertionError("Vyane server did not exit cleanly")
            await wait_for_file(pid_file, timeout=5)
            server_pid = int(pid_file.read_text(encoding="utf-8").strip())
            try:
                os.kill(server_pid, 0)
            except ProcessLookupError:
                pass
            else:
                raise AssertionError("Vyane server process was not reaped")
            return documents


def main() -> None:
    args = parse_args()
    for path in (
        args.qwenpaw_client,
        args.vyane_bin,
        args.upstreams_lock,
    ):
        if not path.is_file():
            raise FileNotFoundError(path)

    documents = asyncio.run(run_flows(args))
    args.evidence_dir.mkdir(parents=True, exist_ok=True)
    for document in documents:
        path = args.evidence_dir / f"vp02-{document['scenario']}.json"
        path.write_text(
            json.dumps(document, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(documents, ensure_ascii=False))


if __name__ == "__main__":
    main()
