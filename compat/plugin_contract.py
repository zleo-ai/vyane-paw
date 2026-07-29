#!/usr/bin/env python3
"""Hermetic contract checks for the installable QwenPaw plugin."""

from __future__ import annotations

import argparse
import ast
import asyncio
import importlib.metadata
import importlib.util
import json
import sys
import time
import types
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_DIR = ROOT / "qwenpaw-plugin"


def load_plugin_module() -> Any:
    path = PLUGIN_DIR / "plugin.py"
    spec = importlib.util.spec_from_file_location("vyane_paw_plugin", path)
    if spec is None or spec.loader is None:
        raise AssertionError("plugin module could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_qwenpaw_manifest_type(path: Path) -> Any:
    qwenpaw_dir = path.parent.parent
    qwenpaw_package = types.ModuleType("qwenpaw")
    qwenpaw_package.__path__ = [str(qwenpaw_dir)]
    plugins_package = types.ModuleType("qwenpaw.plugins")
    plugins_package.__path__ = [str(qwenpaw_dir / "plugins")]
    sys.modules["qwenpaw"] = qwenpaw_package
    sys.modules["qwenpaw.plugins"] = plugins_package
    name = "qwenpaw.plugins.architecture"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AssertionError("pinned QwenPaw manifest parser could not be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module.PluginManifest


def method_parameters(path: Path, class_name: str, method_name: str) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if (
                    isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and item.name == method_name
                ):
                    positional = [arg.arg for arg in item.args.args]
                    keyword_only = [arg.arg for arg in item.args.kwonlyargs]
                    return set(positional + keyword_only)
    raise AssertionError(f"{class_name}.{method_name} is missing from {path}")


def assert_pinned_qwenpaw_api(architecture_path: Path) -> None:
    qwenpaw_dir = architecture_path.parent.parent
    api_path = qwenpaw_dir / "plugins" / "api.py"
    hooks_path = qwenpaw_dir / "runtime" / "hooks.py"
    runtime_path = qwenpaw_dir / "runtime" / "runtime.py"
    builtin_path = qwenpaw_dir / "runtime" / "builtin_commands.py"

    slash = method_parameters(api_path, "PluginApi", "register_slash_command")
    if not {
        "name",
        "handler",
        "aliases",
        "category",
        "help_text",
        "metadata",
    }.issubset(slash):
        raise AssertionError("pinned slash-command API is incompatible")
    skills = method_parameters(api_path, "PluginApi", "register_skill_provider")
    if not {"skills_dir", "enabled_by_default", "channels"}.issubset(skills):
        raise AssertionError("pinned Skill-provider API is incompatible")
    injection = method_parameters(hooks_path, "HookContext", "inject_context")
    if not {"content", "priority", "source"}.issubset(injection):
        raise AssertionError("pinned context-injection API is incompatible")

    runtime_source = runtime_path.read_text(encoding="utf-8")
    if (
        "cmd_msg = await cmd_registry.dispatch" not in runtime_source
        or "if cmd_msg is not None:" not in runtime_source
    ):
        raise AssertionError("pinned slash-command return semantics drifted")
    builtin_source = builtin_path.read_text(encoding="utf-8")
    if 'TextBlock(type="text", text=text)' not in builtin_source:
        raise AssertionError("pinned QwenPaw message construction drifted")


class FakeApi:
    def __init__(self) -> None:
        self.command: tuple[Any, ...] | None = None
        self.skill_provider: tuple[Any, ...] | None = None

    def register_slash_command(self, *args: Any, **kwargs: Any) -> None:
        self.command = (args, kwargs)

    def register_skill_provider(self, *args: Any, **kwargs: Any) -> None:
        self.skill_provider = (args, kwargs)


class FakeContext:
    def __init__(self) -> None:
        self.injections: list[tuple[str, dict[str, Any]]] = []

    def inject_context(self, content: str, **kwargs: Any) -> None:
        self.injections.append((content, kwargs))


def assert_manifest(qwenpaw_architecture: Path | None) -> None:
    manifest = json.loads((PLUGIN_DIR / "plugin.json").read_text(encoding="utf-8"))
    if manifest["id"] != "vyane-paw":
        raise AssertionError("unexpected plugin id")
    if manifest["entry"]["backend"] != "plugin.py":
        raise AssertionError("unexpected plugin entry")
    if manifest["qwenpaw_version"] != {
        "min": "2.1.0b1",
        "max": "2.2.0",
    }:
        raise AssertionError("plugin compatibility window drifted")
    if qwenpaw_architecture is not None:
        parsed = load_qwenpaw_manifest_type(qwenpaw_architecture).from_dict(
            manifest,
        )
        if parsed.id != "vyane-paw" or parsed.entry.backend != "plugin.py":
            raise AssertionError("pinned QwenPaw rejected the plugin manifest")
        assert_pinned_qwenpaw_api(qwenpaw_architecture)
    skill = PLUGIN_DIR / "skills" / "vyane-paw" / "SKILL.md"
    if not skill.is_file():
        raise AssertionError("plugin Skill is missing")


async def assert_command_contract(module: Any) -> None:
    api = FakeApi()
    module.plugin.register(api)
    if api.command is None or api.skill_provider is None:
        raise AssertionError("plugin did not register both entry points")
    command_args, command_kwargs = api.command
    if command_args[0] != "vyane":
        raise AssertionError("unexpected slash command")
    if command_kwargs["category"] != "plugin":
        raise AssertionError("unexpected command category")
    skill_args, skill_kwargs = api.skill_provider
    if Path(skill_kwargs["skills_dir"]) != PLUGIN_DIR / "skills":
        raise AssertionError("unexpected Skill source")
    if not skill_kwargs["enabled_by_default"]:
        raise AssertionError("Vyane Paw Skill must be enabled by default")

    handler = command_args[1]
    cases = {
        "route ROUTE_TASK_SENTINEL": ("route", None),
        "dispatch DISPATCH_TASK_SENTINEL": ("dispatch", None),
        "failover resilient -- FAILOVER_TASK_SENTINEL": (
            "failover",
            "resilient",
        ),
        "review reviewer-a,reviewer-b -- REVIEW_TASK_SENTINEL": (
            "review",
            "reviewer-a,reviewer-b",
        ),
    }
    for raw, (mode, selector) in cases.items():
        ctx = FakeContext()
        response = await handler(ctx, raw)
        if response is not None or len(ctx.injections) != 1:
            raise AssertionError(f"{mode} did not inject exactly one contract")
        content, metadata = ctx.injections[0]
        if f'"mode":"{mode}"' not in content:
            raise AssertionError(f"{mode} was not preserved")
        if selector and selector in content:
            raise AssertionError(f"{mode} selector entered system context")
        if "TASK_SENTINEL" in content:
            raise AssertionError("user task was promoted into system context")
        expected_tool = {
            "route": "vyane_route",
            "dispatch": "vyane_dispatch",
            "failover": "vyane_dispatch",
            "review": "vyane_broadcast",
        }[mode]
        if expected_tool not in content:
            raise AssertionError(f"{mode} did not bind the expected MCP tool")
        if metadata != {"priority": 20, "source": "plugin:vyane-paw"}:
            raise AssertionError("unexpected context injection metadata")

    invalid = (
        "",
        "review only-one -- task",
        "review a,a -- task",
        "review a,,b -- task",
        "review a,b,c,d,e -- task",
        "review a,bad target -- task",
        "failover a,b -- task",
        "failover bad/target -- task",
    )
    for raw in invalid:
        try:
            module.parse_command(raw)
        except ValueError:
            continue
        raise AssertionError(f"invalid command was accepted: {raw!r}")


def assert_launcher() -> None:
    launcher = ROOT / "bin" / "vyane-paw-mcp"
    if not launcher.is_file():
        raise AssertionError("MCP launcher is missing")
    if "/absolute/path" in launcher.read_text(encoding="utf-8"):
        raise AssertionError("launcher contains a fixed path")


def assert_mcp_import() -> int:
    payload = json.loads(
        (ROOT / "config" / "examples" / "qwenpaw-mcp.example.json").read_text(
            encoding="utf-8",
        ),
    )
    client = payload["mcpServers"]["vyane-paw"]
    if client["command"] != "vyane-paw-mcp":
        raise AssertionError("MCP import bypasses the validated launcher")
    required = {"vyane_route", "vyane_dispatch", "vyane_broadcast"}
    if set(client["tools"]) != required:
        raise AssertionError("MCP allowlist exceeds the product tool surface")
    env = client.get("env", {})
    if set(env) != {"VYANE_PAW_CONFIG"}:
        raise AssertionError("example MCP environment is not minimal")
    return len(client["tools"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qwenpaw-architecture", type=Path)
    parser.add_argument("--upstreams-lock", type=Path)
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()
    if (args.upstreams_lock is None) != (args.evidence is None):
        parser.error("--upstreams-lock and --evidence must be used together")
    if (
        args.qwenpaw_architecture is not None
        and not args.qwenpaw_architecture.is_file()
    ):
        raise FileNotFoundError(args.qwenpaw_architecture)
    started_at = datetime.now(UTC)
    started = time.monotonic()
    assert_manifest(args.qwenpaw_architecture)
    module = load_plugin_module()
    asyncio.run(assert_command_contract(module))
    assert_launcher()
    allowlisted_tools = assert_mcp_import()
    if args.evidence is not None:
        lock = json.loads(args.upstreams_lock.read_text(encoding="utf-8"))
        upstreams = lock["upstreams"]
        evidence = {
            "schema_version": "0.1.0",
            "scenario": "product_entry",
            "sanitization_state": "sanitized",
            "started_at": started_at.isoformat(),
            "duration_ms": round((time.monotonic() - started) * 1000),
            "upstream_revisions": {
                "qwenpaw": upstreams["qwenpaw"]["revision"],
                "vyane_rs": upstreams["vyane_rs"]["revision"],
                "rmcp": upstreams["rmcp"]["version"],
                "python_mcp": importlib.metadata.version("mcp"),
            },
            "result": "passed",
            "metrics": {
                "registered_commands": 1,
                "registered_skills": 1,
                "validated_product_modes": 4,
                "allowlisted_mcp_tools": allowlisted_tools,
                "pinned_runtime_contracts": (
                    6 if args.qwenpaw_architecture is not None else 0
                ),
                "fixed_private_paths": 0,
            },
            "limitations": [
                "pinned QwenPaw APIs are verified structurally, not through a full UI session",
                "synthetic commands only; no paid model invocation",
                "MCP DriverCard import remains a separate operator step",
            ],
        }
        args.evidence.parent.mkdir(parents=True, exist_ok=True)
        args.evidence.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print("QwenPaw plugin contract passed.")


if __name__ == "__main__":
    main()
