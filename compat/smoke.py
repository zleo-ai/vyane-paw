#!/usr/bin/env python3
"""Cross-language compatibility smoke test for pinned QwenPaw and vyane-rs."""

from __future__ import annotations

import argparse
import asyncio
import importlib.metadata
import importlib.util
import json
import os
import stat
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


EXPECTED_TOOLS = [
    "vyane_broadcast",
    "vyane_check",
    "vyane_dispatch",
    "vyane_history",
    "vyane_route",
    "vyane_sessions",
    "vyane_workflow_cancel",
    "vyane_workflow_status",
    "vyane_workflow_submit",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qwenpaw-client", type=Path, required=True)
    parser.add_argument("--vyane-bin", type=Path, required=True)
    parser.add_argument(
        "--compatibility-lane",
        choices=("stable", "candidate"),
        required=True,
    )
    parser.add_argument("--vyane-revision", required=True)
    parser.add_argument("--rmcp-version", required=True)
    parser.add_argument("--upstreams-lock", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    return parser.parse_args()


def load_qwenpaw_client(source: Path) -> type[Any]:
    spec = importlib.util.spec_from_file_location(
        "vyane_paw_qwenpaw_mcp_stateful_client",
        source,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load the pinned QwenPaw MCP client")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.StdIOStatefulClient


def result_payload(result: Any) -> dict[str, Any]:
    if not result.content:
        raise AssertionError("MCP result has no content")
    text = getattr(result.content[0], "text", None)
    if not isinstance(text, str):
        raise AssertionError("MCP result does not contain text JSON")
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise AssertionError("MCP result payload is not an object")
    return payload


def revision_map(
    lock_path: Path,
    rmcp_version: str,
    *,
    compatibility_lane: str | None = None,
    vyane_revision: str | None = None,
) -> dict[str, str]:
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    upstreams = lock["upstreams"]
    if vyane_revision is None:
        vyane_revision = upstreams["vyane_rs"]["revision"]
    revisions = {
        "qwenpaw": upstreams["qwenpaw"]["revision"],
        "vyane_rs": vyane_revision,
        "rmcp": rmcp_version,
        "python_mcp": importlib.metadata.version("mcp"),
    }
    if compatibility_lane is not None:
        revisions["compatibility_lane"] = compatibility_lane
    return revisions


async def wait_for_file(path: Path, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while not path.is_file():
        if time.monotonic() >= deadline:
            raise AssertionError(f"timed out waiting for {path.name}")
        await asyncio.sleep(0.05)


def write_server_launcher(root: Path) -> tuple[Path, Path, Path]:
    launcher = root / "launch-vyane.sh"
    pid_file = root / "server.pid"
    exit_status_file = root / "server-exit-status"
    launcher.write_text(
        """#!/usr/bin/env bash
set +e
"${VYANE_PAW_SERVER_BIN:?}" "$@" <&0 >&1 2>&2 &
server_pid="$!"
printf '%s\\n' "$server_pid" >"${VYANE_PAW_SERVER_PID_FILE:?}"
wait "$server_pid"
server_status="$?"
printf '%s\\n' "$server_status" >"${VYANE_PAW_SERVER_EXIT_FILE:?}"
exit "$server_status"
""",
        encoding="utf-8",
    )
    launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)
    return launcher, pid_file, exit_status_file


async def run_smoke(args: argparse.Namespace) -> dict[str, Any]:
    client_type = load_qwenpaw_client(args.qwenpaw_client)
    started = time.monotonic()

    with tempfile.TemporaryDirectory(prefix="vyane-paw-vp01-") as temp:
        root = Path(temp)
        for name in ("home", "config", "data", "work"):
            (root / name).mkdir()
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
            name="vyane-paw-vp01",
            command=str(launcher),
            args=["mcp"],
            env=child_env,
            cwd=str(root / "work"),
            read_timeout_seconds=30,
        )

        try:
            await client.connect(timeout=30)
            tools = await client.list_tools()
            tool_names = sorted(str(tool.name) for tool in tools)
            if tool_names != EXPECTED_TOOLS:
                raise AssertionError(
                    f"unexpected tool set: {tool_names}",
                )

            success = result_payload(
                await client.call_tool("vyane_sessions", {}),
            )
            if success != {"items": []}:
                raise AssertionError(
                    f"vyane_sessions returned unexpected data: {success!r}",
                )

            rejected = result_payload(
                await client.call_tool(
                    "vyane_sessions",
                    {"unexpected": "synthetic"},
                ),
            )
            if rejected.get("status") != "error":
                raise AssertionError("invalid arguments were not rejected")
            if rejected.get("error", {}).get("code") != "invalid_argument":
                raise AssertionError("invalid arguments used the wrong code")
        finally:
            await client.close(ignore_errors=False)

        # VP-01 deliberately couples to the pinned QwenPaw lifecycle seam:
        # public disconnection alone cannot prove its background task exited.
        if client.is_connected or client._lifecycle_task is not None:
            raise AssertionError("QwenPaw client lifecycle did not close")

        await wait_for_file(pid_file, timeout=5)
        await wait_for_file(exit_status_file, timeout=5)
        server_pid = int(pid_file.read_text(encoding="utf-8").strip())
        server_exit_code = int(
            exit_status_file.read_text(encoding="utf-8").strip(),
        )
        if server_exit_code != 0:
            raise AssertionError(
                f"Vyane server exited with code {server_exit_code}",
            )
        try:
            os.kill(server_pid, 0)
        except ProcessLookupError:
            server_process_reaped = 1
        else:
            raise AssertionError("Vyane server process was not reaped")

    return {
        "schema_version": "0.1.0",
        "scenario": "compatibility",
        "sanitization_state": "sanitized",
        "started_at": datetime.now(UTC).isoformat(),
        "duration_ms": round((time.monotonic() - started) * 1000),
        "upstream_revisions": revision_map(
            args.upstreams_lock,
            args.rmcp_version,
            compatibility_lane=args.compatibility_lane,
            vyane_revision=args.vyane_revision,
        ),
        "result": "passed",
        "metrics": {
            "discovered_tools": len(EXPECTED_TOOLS),
            "successful_calls": 1,
            "rejected_invalid_calls": 1,
            "server_exit_code": server_exit_code,
            "server_process_reaped": server_process_reaped,
        },
        "limitations": [
            "stdio transport only",
            "isolated QwenPaw MCP client module, not the full QwenPaw application",
            "no provider or model invocation",
        ],
    }


def main() -> None:
    args = parse_args()
    for path in (
        args.qwenpaw_client,
        args.vyane_bin,
        args.upstreams_lock,
    ):
        if not path.is_file():
            raise FileNotFoundError(path)

    evidence = asyncio.run(run_smoke(args))
    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    args.evidence.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(evidence, ensure_ascii=False))


if __name__ == "__main__":
    main()
