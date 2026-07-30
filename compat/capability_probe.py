#!/usr/bin/env python3
"""MCP capability-negotiation probe for pinned QwenPaw and vyane-rs (VP-09).

The probe observes and records; it never claims product support. It performs
two launches of the pinned Vyane MCP server:

1. A direct SDK ``ClientSession`` (same locked ``mcp`` dependency the pinned
   QwenPaw client constrains) captures the full ``InitializeResult`` verbatim
   and runs one bounded ``server/discover`` method probe.
2. The pinned, unmodified QwenPaw ``StdIOStatefulClient`` completes its
   lifecycle against the same server and must observe identical server
   capabilities; the launcher's exit status and process reaping are asserted
   exactly as in the VP-01 smoke.
"""

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
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from mcp import types
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.shared.exceptions import McpError
from mcp.shared.version import SUPPORTED_PROTOCOL_VERSIONS


class ServerDiscoverRequest(
    types.Request[types.RequestParams | None, Literal["server/discover"]],
):
    """One bounded probe for the optional ``server/discover`` method.

    Declared with public ``mcp.types`` generics only. A method-not-found
    error is an observation, not a failure; the server is never retried,
    patched, or worked around.
    """

    method: Literal["server/discover"] = "server/discover"
    params: types.RequestParams | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qwenpaw-client", type=Path)
    parser.add_argument("--vyane-bin", type=Path)
    parser.add_argument(
        "--compatibility-lane",
        choices=("stable", "candidate"),
        default="stable",
    )
    parser.add_argument("--vyane-revision")
    parser.add_argument("--rmcp-version")
    parser.add_argument("--upstreams-lock", type=Path)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run the negative parity fixture and exit",
    )
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


def child_environment(root: Path) -> dict[str, str]:
    return {
        "HOME": str(root / "home"),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "RUST_LOG": "warn",
        "VYANE_DATA_DIR": str(root / "data"),
        "XDG_CONFIG_HOME": str(root / "config"),
    }


def capability_snapshot(capabilities: types.ServerCapabilities) -> dict[str, Any]:
    snapshot = capabilities.model_dump(by_alias=True, exclude_none=True)
    if not isinstance(snapshot, dict):
        raise AssertionError("server capabilities did not serialize to an object")
    return snapshot


def assert_capability_parity(
    direct: dict[str, Any],
    qwenpaw_observed: dict[str, Any],
) -> None:
    if direct != qwenpaw_observed:
        raise AssertionError(
            "the QwenPaw client and the direct session observed different "
            f"server capabilities: direct={sorted(direct)} "
            f"qwenpaw={sorted(qwenpaw_observed)}",
        )


def run_self_test() -> int:
    assert_capability_parity({"tools": {}}, {"tools": {}})
    try:
        assert_capability_parity({"tools": {}}, {"tools": {}, "tasks": {}})
    except AssertionError:
        pass
    else:
        print("parity check accepted a capability mismatch", flush=True)
        return 1
    print("capability-probe self-test passed.")
    return 0


async def run_direct_session(
    args: argparse.Namespace,
    root: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Capture the verbatim InitializeResult and probe ``server/discover``."""
    env = child_environment(root)
    parameters = StdioServerParameters(
        command=str(args.vyane_bin),
        args=["mcp"],
        env=env,
        cwd=str(root / "work"),
    )
    async with stdio_client(parameters) as (read_stream, write_stream):
        async with ClientSession(
            read_stream,
            write_stream,
            read_timeout_seconds=timedelta(seconds=30),
        ) as session:
            initialize_result = await session.initialize()

            try:
                await session.send_request(ServerDiscoverRequest(), types.Result)
                discover_probe: dict[str, Any] = {"outcome": "ok"}
            except McpError as error:
                discover_probe = {
                    "outcome": "error",
                    "error_code": error.error.code,
                }

    capabilities = capability_snapshot(initialize_result.capabilities)
    snapshot = {
        "negotiated_protocol_version": initialize_result.protocolVersion,
        "server_name": initialize_result.serverInfo.name,
        "server_version": initialize_result.serverInfo.version,
        "server_instructions_present": initialize_result.instructions is not None,
        "server_capability_keys": sorted(capabilities),
        "client_supported_protocol_versions": sorted(
            SUPPORTED_PROTOCOL_VERSIONS,
        ),
        "discover_probe": discover_probe,
        "product_claimed": [],
    }
    return snapshot, capabilities, discover_probe


async def run_qwenpaw_parity_session(
    args: argparse.Namespace,
    root: Path,
    direct_capabilities: dict[str, Any],
) -> dict[str, int]:
    """Prove lifecycle parity and clean shutdown through the pinned client."""
    client_type = load_qwenpaw_client(args.qwenpaw_client)
    launcher, pid_file, exit_status_file = write_server_launcher(root)
    env = child_environment(root)
    env.update(
        {
            "VYANE_PAW_SERVER_BIN": str(args.vyane_bin),
            "VYANE_PAW_SERVER_EXIT_FILE": str(exit_status_file),
            "VYANE_PAW_SERVER_PID_FILE": str(pid_file),
        },
    )
    client = client_type(
        name="vyane-paw-vp09",
        command=str(launcher),
        args=["mcp"],
        env=env,
        cwd=str(root / "work"),
        read_timeout_seconds=30,
    )

    try:
        await client.connect(timeout=30)
        session = client.session
        if session is None:
            raise AssertionError("QwenPaw client connected without a session")
        observed = session.get_server_capabilities()
        if observed is None:
            raise AssertionError("QwenPaw client session is not initialized")
        assert_capability_parity(
            direct_capabilities,
            capability_snapshot(observed),
        )
    finally:
        await client.close(ignore_errors=False)

    # Same lifecycle seam as the VP-01 smoke: public disconnection alone
    # cannot prove the background task exited.
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
        "server_exit_code": server_exit_code,
        "server_process_reaped": server_process_reaped,
    }


async def run_probe(args: argparse.Namespace) -> dict[str, Any]:
    started = time.monotonic()

    with tempfile.TemporaryDirectory(prefix="vyane-paw-vp09-") as temp:
        root = Path(temp)
        for name in ("home", "config", "data", "work"):
            (root / name).mkdir()

        snapshot, direct_capabilities, discover_probe = await run_direct_session(
            args,
            root,
        )
        lifecycle_metrics = await run_qwenpaw_parity_session(
            args,
            root,
            direct_capabilities,
        )

    return {
        "schema_version": "0.1.0",
        "scenario": "capability_probe",
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
            "discover_probe_available": int(discover_probe["outcome"] == "ok"),
            "discover_probe_completed": 1,
            "product_claimed_extensions": 0,
            "qwenpaw_client_lifecycle_closed": 1,
            "qwenpaw_client_parity": 1,
            "server_advertises_tasks": int("tasks" in direct_capabilities),
            **lifecycle_metrics,
        },
        "capabilities": snapshot,
        "limitations": [
            "stdio transport only",
            "observation only; no MCP extension is claimed as a product feature",
            "isolated QwenPaw MCP client module, not the full QwenPaw application",
            "no provider or model invocation",
        ],
    }


def main() -> None:
    args = parse_args()
    if args.self_test:
        raise SystemExit(run_self_test())

    args.qwenpaw_client = args.qwenpaw_client.resolve()
    args.vyane_bin = args.vyane_bin.resolve()
    args.upstreams_lock = args.upstreams_lock.resolve()
    args.evidence = args.evidence.resolve()
    for path in (
        args.qwenpaw_client,
        args.vyane_bin,
        args.upstreams_lock,
    ):
        if not path.is_file():
            raise FileNotFoundError(path)

    evidence = asyncio.run(run_probe(args))
    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    args.evidence.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(evidence, ensure_ascii=False))


if __name__ == "__main__":
    main()
