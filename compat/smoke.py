#!/usr/bin/env python3
"""Cross-language compatibility smoke test for pinned QwenPaw and vyane-rs."""

from __future__ import annotations

import argparse
import asyncio
import importlib.metadata
import importlib.util
import json
import os
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


def revision_map(lock_path: Path) -> dict[str, str]:
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    upstreams = lock["upstreams"]
    return {
        "qwenpaw": upstreams["qwenpaw"]["revision"],
        "vyane_rs": upstreams["vyane_rs"]["revision"],
        "rmcp": upstreams["rmcp"]["version"],
        "python_mcp": importlib.metadata.version("mcp"),
    }


async def run_smoke(args: argparse.Namespace) -> dict[str, Any]:
    client_type = load_qwenpaw_client(args.qwenpaw_client)
    started = time.monotonic()

    with tempfile.TemporaryDirectory(prefix="vyane-paw-vp01-") as temp:
        root = Path(temp)
        for name in ("home", "config", "data", "work"):
            (root / name).mkdir()

        child_env = {
            "HOME": str(root / "home"),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "RUST_LOG": "warn",
            "VYANE_DATA_DIR": str(root / "data"),
            "XDG_CONFIG_HOME": str(root / "config"),
        }
        client = client_type(
            name="vyane-paw-vp01",
            command=str(args.vyane_bin),
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

    return {
        "schema_version": "0.1.0",
        "scenario": "compatibility",
        "sanitization_state": "sanitized",
        "started_at": datetime.now(UTC).isoformat(),
        "duration_ms": round((time.monotonic() - started) * 1000),
        "upstream_revisions": revision_map(args.upstreams_lock),
        "result": "passed",
        "metrics": {
            "discovered_tools": len(EXPECTED_TOOLS),
            "successful_calls": 1,
            "rejected_invalid_calls": 1,
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
