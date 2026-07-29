#!/usr/bin/env python3
"""Hermetic contract checks for the installable QwenPaw plugin."""

from __future__ import annotations

import argparse
import ast
import asyncio
import importlib.metadata
import importlib.util
import json
import os
import sys
import tempfile
import time
import types
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_DIR = ROOT / "qwenpaw-plugin"


@cache
def operation_result_validator() -> Any:
    from jsonschema.validators import validator_for

    schema = json.loads(
        (ROOT / "schemas" / "operation-result.schema.json").read_text(
            encoding="utf-8",
        ),
    )
    validator_class = validator_for(schema)
    validator_class.check_schema(schema)
    return validator_class(schema)


def assert_operation_result_schema(instance: dict[str, Any]) -> None:
    errors = sorted(
        operation_result_validator().iter_errors(instance),
        key=lambda error: error.path,
    )
    if errors:
        raise AssertionError(
            "normalized result violates operation-result schema: "
            + "; ".join(error.message for error in errors),
        )


def load_plugin_module() -> Any:
    path = PLUGIN_DIR / "plugin.py"
    name = "vyane_paw_plugin"
    spec = importlib.util.spec_from_file_location(
        name,
        path,
        submodule_search_locations=[str(PLUGIN_DIR)],
    )
    if spec is None or spec.loader is None:
        raise AssertionError("plugin module could not be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    module.__package__ = name
    module.__path__ = [str(PLUGIN_DIR)]
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
    if not path.is_file():
        raise AssertionError(f"pinned QwenPaw source is missing: {path.name}")
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


def assert_pinned_qwenpaw_api(architecture_path: Path) -> int:
    qwenpaw_dir = architecture_path.parent.parent
    api_path = qwenpaw_dir / "plugins" / "api.py"
    hooks_path = qwenpaw_dir / "runtime" / "hooks.py"
    runtime_path = qwenpaw_dir / "runtime" / "runtime.py"
    builtin_path = qwenpaw_dir / "runtime" / "builtin_commands.py"
    builder_path = qwenpaw_dir / "runtime" / "builder.py"
    for path in (api_path, hooks_path, runtime_path, builtin_path, builder_path):
        if not path.is_file():
            raise AssertionError(f"pinned QwenPaw source is missing: {path.name}")

    verified = 0
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
    verified += 1
    skills = method_parameters(api_path, "PluginApi", "register_skill_provider")
    if not {"skills_dir", "enabled_by_default", "channels"}.issubset(skills):
        raise AssertionError("pinned Skill-provider API is incompatible")
    verified += 1
    middleware = method_parameters(api_path, "PluginApi", "register_middleware")
    if not {"middleware_factory", "priority"}.issubset(middleware):
        raise AssertionError("pinned middleware API is incompatible")
    verified += 1
    injection = method_parameters(hooks_path, "HookContext", "inject_context")
    if not {"content", "priority", "source"}.issubset(injection):
        raise AssertionError("pinned context-injection API is incompatible")
    verified += 1

    runtime_source = runtime_path.read_text(encoding="utf-8")
    if "cmd_msg = await cmd_registry.dispatch" not in runtime_source:
        raise AssertionError("pinned slash-command dispatch semantics drifted")
    verified += 1
    if "if cmd_msg is not None:" not in runtime_source:
        raise AssertionError("pinned slash-command return semantics drifted")
    verified += 1
    builtin_source = builtin_path.read_text(encoding="utf-8")
    if 'TextBlock(type="text", text=text)' not in builtin_source:
        raise AssertionError("pinned QwenPaw message construction drifted")
    verified += 1
    builder_source = builder_path.read_text(encoding="utf-8")
    if 'getattr(request, "request_context", None)' not in builder_source:
        raise AssertionError("pinned request-context propagation drifted")
    verified += 1
    if (
        'get("subagent_allowed_tools")' not in builder_source
        or "return [t for t in items if cls._tool_name(t) in allow]"
        not in builder_source
    ):
        raise AssertionError("pinned request tool-whitelist contract drifted")
    verified += 1
    return verified


class FakeApi:
    def __init__(self) -> None:
        self.command: tuple[Any, ...] | None = None
        self.skill_provider: tuple[Any, ...] | None = None
        self.middleware: tuple[Any, ...] | None = None

    def register_slash_command(self, *args: Any, **kwargs: Any) -> None:
        self.command = (args, kwargs)

    def register_skill_provider(self, *args: Any, **kwargs: Any) -> None:
        self.skill_provider = (args, kwargs)

    def register_middleware(self, *args: Any, **kwargs: Any) -> None:
        self.middleware = (args, kwargs)


class FakeContext:
    def __init__(self) -> None:
        self.injections: list[tuple[str, dict[str, Any]]] = []
        self.request = types.SimpleNamespace(request_context=None)

    def inject_context(self, content: str, **kwargs: Any) -> None:
        self.injections.append((content, kwargs))


def response_text(response: Any) -> str:
    """Extract text without depending on a fake AgentScope message shape."""
    parts: list[str] = []
    for block in getattr(response, "content", []) or []:
        text = (
            block.get("text")
            if isinstance(block, Mapping)
            else getattr(block, "text", None)
        )
        if isinstance(text, str):
            parts.append(text)
    return "\n".join(parts)


def assert_bounded_denial(response: Any, forbidden: Iterable[str]) -> None:
    if response is None:
        raise AssertionError("policy denial did not return a bounded response")
    text = response_text(response)
    if not text:
        raise AssertionError("policy denial response has no text")
    leaked = [value for value in forbidden if value and value in text]
    if leaked:
        raise AssertionError("policy denial exposed deployment-owned input")


def assert_manifest(qwenpaw_architecture: Path | None) -> int:
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
        runtime_contracts = assert_pinned_qwenpaw_api(qwenpaw_architecture)
    else:
        runtime_contracts = 0
    skill = PLUGIN_DIR / "skills" / "vyane-paw" / "SKILL.md"
    if not skill.is_file():
        raise AssertionError("plugin Skill is missing")
    return runtime_contracts


async def assert_command_contract(module: Any) -> dict[str, int]:
    api = FakeApi()
    module.plugin.register(api)
    if api.command is None or api.skill_provider is None or api.middleware is None:
        raise AssertionError("plugin did not register every entry point")
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
    middleware_args, middleware_kwargs = api.middleware
    if middleware_args[0] is not module._result_middleware_factory:
        raise AssertionError("unexpected result middleware factory")
    if middleware_kwargs != {"priority": 40}:
        raise AssertionError("unexpected result middleware priority")

    handler = command_args[1]
    request_scoped_tool_boundaries = 0
    policy = {
        "schema_version": "0.1.0",
        "profile": "contract-test",
        "allowed_tools": [
            "vyane_route",
            "vyane_dispatch",
            "vyane_broadcast",
        ],
        "allow_failover": True,
        "allow_broadcast": True,
        "max_parallel_targets": 2,
        "allowed_targets": ["resilient", "reviewer-a", "reviewer-b"],
    }
    with tempfile.TemporaryDirectory() as tmp:
        policy_path = Path(tmp) / "policy.json"
        policy_path.write_text(json.dumps(policy), encoding="utf-8")
        previous_policy = os.environ.get("VYANE_PAW_POLICY")
        os.environ["VYANE_PAW_POLICY"] = str(policy_path)
        try:
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
                ctx.request.request_context = {
                    "trace_marker": "preserved",
                    "subagent_allowed_tools": ["must-be-replaced"],
                }
                response = await handler(ctx, raw)
                if response is not None or len(ctx.injections) != 1:
                    raise AssertionError(
                        f"{mode} did not inject exactly one contract",
                    )
                content, metadata = ctx.injections[0]
                if f'"mode":"{mode}"' not in content:
                    raise AssertionError(f"{mode} was not preserved")
                if selector and selector in content:
                    raise AssertionError(
                        f"{mode} selector entered system context",
                    )
                if "TASK_SENTINEL" in content:
                    raise AssertionError(
                        "user task was promoted into system context",
                    )
                expected_tool = {
                    "route": "vyane_route",
                    "dispatch": "vyane_dispatch",
                    "failover": "vyane_dispatch",
                    "review": "vyane_broadcast",
                }[mode]
                if f"Required MCP tool: {expected_tool}\n" not in content:
                    raise AssertionError(
                        f"{mode} did not bind the expected MCP tool",
                    )
                if ctx.request.request_context != {
                    "trace_marker": "preserved",
                    "subagent_allowed_tools": [expected_tool],
                    "vyane_paw_result_contract": {
                        "tool": expected_tool,
                        "mode": mode,
                        "policy_profile": "contract-test",
                    },
                }:
                    raise AssertionError(
                        f"{mode} did not enforce its request tool boundary",
                    )
                if "Enforced policy profile: contract-test" not in content:
                    raise AssertionError("policy identity was not preserved")
                arguments_line = next(
                    (
                        line
                        for line in content.splitlines()
                        if line.startswith("Fixed MCP arguments: ")
                    ),
                    None,
                )
                if arguments_line is None:
                    raise AssertionError(
                        f"{mode} has no fixed MCP argument contract",
                    )
                fixed_arguments = json.loads(
                    arguments_line.removeprefix("Fixed MCP arguments: "),
                )
                expected_arguments = {
                    "route": {"allow_frontier": False},
                    "dispatch": {
                        "target": "auto",
                        "allow_frontier": False,
                        "sandbox": "read_only",
                        "timeout_secs": 120,
                    },
                    "failover": {
                        "allow_frontier": False,
                        "sandbox": "read_only",
                        "timeout_secs": 120,
                    },
                    "review": {
                        "sandbox": "read_only",
                        "timeout_secs": 120,
                    },
                }[mode]
                if fixed_arguments != expected_arguments:
                    raise AssertionError(
                        f"{mode} fixed MCP arguments drifted",
                    )
                if metadata != {
                    "priority": 20,
                    "source": "plugin:vyane-paw",
                }:
                    raise AssertionError(
                        "unexpected context injection metadata",
                    )
                request_scoped_tool_boundaries += 1
        finally:
            if previous_policy is None:
                os.environ.pop("VYANE_PAW_POLICY", None)
            else:
                os.environ["VYANE_PAW_POLICY"] = previous_policy

    enforced_policy_denials = await assert_policy_enforcement(module, handler)
    assert_policy_validation(module)
    normalized_result_cases = assert_result_contract(module)
    result_middleware_rewrites = await assert_result_middleware(module)

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
    return {
        "request_scoped_tool_boundaries": request_scoped_tool_boundaries,
        "enforced_policy_denials": enforced_policy_denials,
        "normalized_result_cases": normalized_result_cases,
        "result_middleware_rewrites": result_middleware_rewrites,
    }


def assert_result_contract(module: Any) -> int:
    contract = importlib.import_module(f"{module.__name__}.result_contract")
    normalized_result_cases = 0
    cases = [
        (
            "vyane_route",
            "route",
            {"profile": "safe", "provider": "synthetic", "model": "small"},
            ("completed", "success", "full"),
        ),
        (
            "vyane_dispatch",
            "dispatch",
            {
                "operation_status": "completed",
                "record": {"status": "success"},
                "detail_omitted": False,
            },
            ("completed", "success", "full"),
        ),
        (
            "vyane_dispatch",
            "failover",
            {
                "operation_status": "completed",
                "receipt": {"run_status": "failed"},
                "detail_omitted": True,
            },
            ("completed", "failure", "receipt"),
        ),
        (
            "vyane_broadcast",
            "review",
            {
                "operation_status": "completed",
                "items": [
                    {"record": {"status": "success"}},
                    {"error": {"code": "unavailable"}},
                ],
                "detail_omitted": False,
            },
            ("completed", "partial", "full"),
        ),
    ]
    for tool, mode, payload, expected in cases:
        normalized = contract.normalize_tool_payload(
            tool=tool,
            mode=mode,
            policy_profile="contract-test",
            payload=payload,
        )
        actual = (
            normalized["operation_status"],
            normalized["outcome"],
            normalized["detail_state"],
        )
        if actual != expected:
            raise AssertionError(f"{mode} result normalization drifted")
        if normalized["retry_guidance"] != "do_not_retry":
            raise AssertionError(f"{mode} result became retryable")
        assert_operation_result_schema(normalized)
        normalized_result_cases += 1

    rejected = contract.normalize_tool_payload(
        tool="vyane_dispatch",
        mode="dispatch",
        policy_profile="contract-test",
        payload={
            "status": "error",
            "error": {
                "code": "invalid_argument",
                "message": "bounded upstream message",
            },
        },
    )
    if rejected["operation_status"] != "rejected":
        raise AssertionError("safe Vyane rejection was not normalized")
    if rejected["error"] != {"code": "invalid_argument"}:
        raise AssertionError("raw upstream error crossed the result contract")
    if "data" in rejected:
        raise AssertionError("rejected result included completed data")
    assert_operation_result_schema(rejected)
    normalized_result_cases += 1

    malformed = contract.normalize_tool_payload(
        tool="vyane_dispatch",
        mode="dispatch",
        policy_profile="contract-test",
        payload={"operation_status": "running"},
    )
    if malformed["operation_status"] != "protocol_failure":
        raise AssertionError("unexpected operation status did not fail closed")
    assert_operation_result_schema(malformed)
    normalized_result_cases += 1

    transport = contract.normalize_tool_payload(
        tool="vyane_dispatch",
        mode="dispatch",
        policy_profile="contract-test",
        payload={
            "ok": False,
            "type": "driver_unavailable",
            "message": "raw driver detail",
        },
    )
    if transport["operation_status"] != "transport_failure":
        raise AssertionError("driver failure was not normalized")
    if transport["error"] != {"code": "driver_unavailable"}:
        raise AssertionError("driver failure code was not bounded")
    if "message" in transport:
        raise AssertionError("raw driver error crossed the result contract")
    if "data" in transport:
        raise AssertionError("transport failure included completed data")
    assert_operation_result_schema(transport)
    normalized_result_cases += 1

    raw_marker = "must-not-cross-contract"
    projected = contract.normalize_tool_payload(
        tool="vyane_broadcast",
        mode="review",
        policy_profile="contract-test",
        payload={
            "operation_status": "completed",
            "items": [
                {
                    "index": 0,
                    "target": "reviewer-a",
                    "error": {
                        "code": "unavailable",
                        "message": raw_marker,
                    },
                },
            ],
            "detail_omitted": False,
            "raw_error": raw_marker,
        },
    )
    if projected["data"]["items"][0]["error"] != {"code": "unavailable"}:
        raise AssertionError("broadcast error projection drifted")
    if raw_marker in json.dumps(projected):
        raise AssertionError("completed result exposed unbounded upstream data")
    if "error" in projected:
        raise AssertionError("completed result included envelope error")
    assert_operation_result_schema(projected)
    normalized_result_cases += 1

    unknown = contract.normalize_tool_payload(
        tool="vyane_broadcast",
        mode="review",
        policy_profile="contract-test",
        payload={
            "operation_status": "completed",
            "items": [
                {"record": {"status": "success"}},
                {"record": {"status": "future_status"}},
            ],
            "detail_omitted": False,
        },
    )
    if unknown["outcome"] != "unknown":
        raise AssertionError("unknown broadcast status did not fail closed")
    assert_operation_result_schema(unknown)
    normalized_result_cases += 1

    selected = contract.payload_from_text_blocks(
        [
            {
                "type": "text",
                "text": json.dumps(
                    {
                        "operation_status": "completed",
                        "record": {"status": "success"},
                    },
                ),
            },
            {"type": "text", "text": json.dumps({"note": "unrelated"})},
        ],
    )
    if selected is None or selected.get("operation_status") != "completed":
        raise AssertionError("structured result selection drifted")
    return normalized_result_cases


def assert_policy_validation(module: Any) -> None:
    core = importlib.import_module(f"{module.__name__}.core")
    invalid = [
        {
            "schema_version": "0.1.0",
            "profile": "bad-failover",
            "allowed_tools": ["vyane_route"],
            "allow_failover": True,
            "allowed_targets": ["resilient"],
        },
        {
            "schema_version": "0.1.0",
            "profile": "unbounded-targets",
            "allowed_tools": ["vyane_dispatch"],
            "allow_failover": True,
        },
        {
            "schema_version": "0.1.0",
            "profile": "bad-broadcast",
            "allowed_tools": ["vyane_broadcast"],
            "allow_broadcast": True,
            "max_parallel_targets": 1,
            "allowed_targets": ["reviewer-a", "reviewer-b"],
        },
    ]
    for payload in invalid:
        try:
            core.RuntimePolicy.from_mapping(payload)
        except core.PolicyError:
            continue
        raise AssertionError("internally inconsistent policy was accepted")

    policy = core.RuntimePolicy.from_mapping(
        {
            "schema_version": "0.1.0",
            "profile": "strict",
            "allowed_tools": ["vyane_route", "vyane_dispatch", "vyane_broadcast"],
            "allow_failover": True,
            "allow_broadcast": True,
            "max_parallel_targets": 2,
            "allowed_targets": ["reviewer-a", "reviewer-b"],
        },
    )
    malformed_plans = [
        {"mode": "route", "target": "reviewer-a"},
        {"mode": "dispatch", "target": "reviewer-a"},
        {"mode": "failover"},
        {"mode": "failover", "target": "reviewer-c"},
        {"mode": "review", "targets": ["reviewer-a", "reviewer-b"]},
        {"mode": "review", "targets": "reviewer-a,reviewer-a"},
        {"mode": "review", "targets": "reviewer-a,reviewer-c"},
    ]
    for plan in malformed_plans:
        try:
            policy.authorize(plan)
        except core.PolicyError:
            continue
        raise AssertionError("malformed or unauthorized execution plan was accepted")


async def assert_result_middleware(module: Any) -> int:
    from agentscope.message import TextBlock
    from agentscope.middleware import MiddlewareBase
    from agentscope.tool import ToolResponse

    empty_ctx = FakeContext()
    if module._result_middleware_factory(empty_ctx, None) is not None:
        raise AssertionError("result middleware installed without a request contract")

    ctx = FakeContext()
    ctx.request.request_context = {
        "vyane_paw_result_contract": {
            "tool": "vyane_dispatch",
            "mode": "dispatch",
            "policy_profile": "contract-test",
        },
    }
    middleware = module._result_middleware_factory(ctx, None)
    if middleware is None:
        raise AssertionError("result middleware factory returned None")
    if not isinstance(middleware, MiddlewareBase):
        raise AssertionError("result middleware does not implement AgentScope contract")
    response = ToolResponse(
        id="call-contract",
        content=[
            TextBlock(
                type="text",
                text=json.dumps(
                    {
                        "operation_status": "completed",
                        "record": {"status": "success"},
                        "detail_omitted": False,
                    },
                ),
            ),
        ],
        metadata={"existing": "preserved"},
    )

    async def next_handler():
        yield response

    tool_call = types.SimpleNamespace(name="vyane_dispatch")
    events = [
        event
        async for event in middleware.on_acting(
            None,
            {"tool_call": tool_call},
            next_handler,
        )
    ]
    if events != [response] or len(response.content) != 1:
        raise AssertionError("result middleware changed event cardinality")
    normalized = json.loads(response.content[0].text)
    if normalized["operation_status"] != "completed":
        raise AssertionError("result middleware did not normalize payload")
    assert_operation_result_schema(normalized)
    if response.metadata != {
        "existing": "preserved",
        "vyane_paw_result_schema": "0.1.0",
        "vyane_paw_operation_status": "completed",
    }:
        raise AssertionError("result middleware metadata drifted")

    passthrough = ToolResponse(
        id="call-other",
        content=[TextBlock(type="text", text="unchanged")],
        metadata={"existing": "preserved"},
    )

    async def passthrough_handler():
        yield passthrough

    passthrough_events = [
        event
        async for event in middleware.on_acting(
            None,
            {"tool_call": types.SimpleNamespace(name="other_tool")},
            passthrough_handler,
        )
    ]
    if passthrough_events != [passthrough]:
        raise AssertionError("result middleware changed unrelated tool events")
    if passthrough.content[0].text != "unchanged" or passthrough.metadata != {
        "existing": "preserved",
    }:
        raise AssertionError("result middleware mutated an unrelated tool result")
    return 1


async def assert_policy_enforcement(module: Any, handler: Any) -> int:
    enforced_policy_denials = 0
    previous_policy = os.environ.pop("VYANE_PAW_POLICY", None)
    try:
        default_route = FakeContext()
        if await handler(default_route, "route task") is not None:
            raise AssertionError("default policy denied route")
        default_dispatch = FakeContext()
        if await handler(default_dispatch, "dispatch task") is not None:
            raise AssertionError("default policy denied automatic dispatch")
        default_failover = FakeContext()
        denied = await handler(default_failover, "failover resilient -- task")
        if (
            default_failover.injections
            or default_failover.request.request_context is not None
        ):
            raise AssertionError("default policy mutated a denied failover request")
        assert_bounded_denial(denied, ["resilient"])
        enforced_policy_denials += 1

        default_review = FakeContext()
        denied = await handler(default_review, "review reviewer-a,reviewer-b -- task")
        if (
            default_review.injections
            or default_review.request.request_context is not None
        ):
            raise AssertionError("default policy mutated a denied review request")
        assert_bounded_denial(denied, ["reviewer-a", "reviewer-b"])
        enforced_policy_denials += 1

        restrictive = {
            "schema_version": "0.1.0",
            "profile": "restricted",
            "allowed_tools": ["vyane_broadcast"],
            "allow_broadcast": True,
            "max_parallel_targets": 2,
            "allowed_targets": ["reviewer-a", "reviewer-b"],
        }
        with tempfile.TemporaryDirectory() as tmp:
            policy_path = Path(tmp) / "policy.json"
            policy_path.write_text(json.dumps(restrictive), encoding="utf-8")
            os.environ["VYANE_PAW_POLICY"] = str(policy_path)

            denied_route = FakeContext()
            response = await handler(denied_route, "route task")
            if (
                denied_route.injections
                or denied_route.request.request_context is not None
            ):
                raise AssertionError("tool policy did not deny route")
            assert_bounded_denial(response, [str(policy_path)])
            enforced_policy_denials += 1

            too_many = FakeContext()
            response = await handler(
                too_many,
                "review reviewer-a,reviewer-b,reviewer-c -- task",
            )
            if too_many.injections or too_many.request.request_context is not None:
                raise AssertionError(
                    "parallelism policy did not fail closed",
                )
            assert_bounded_denial(
                response,
                ["reviewer-a", "reviewer-b", "reviewer-c", str(policy_path)],
            )
            enforced_policy_denials += 1

            unknown_target = FakeContext()
            response = await handler(
                unknown_target,
                "review reviewer-a,reviewer-c -- task",
            )
            if (
                unknown_target.injections
                or unknown_target.request.request_context is not None
            ):
                raise AssertionError(
                    "target policy did not fail closed",
                )
            assert_bounded_denial(
                response,
                ["reviewer-a", "reviewer-c", str(policy_path)],
            )
            enforced_policy_denials += 1

            policy_path.write_text("{invalid", encoding="utf-8")
            invalid_policy = FakeContext()
            response = await handler(invalid_policy, "route task")
            if (
                invalid_policy.injections
                or invalid_policy.request.request_context is not None
            ):
                raise AssertionError(
                    "invalid policy did not fail closed",
                )
            assert_bounded_denial(response, [str(policy_path)])
            enforced_policy_denials += 1

            missing_path = Path(tmp) / "missing-policy.json"
            os.environ["VYANE_PAW_POLICY"] = str(missing_path)
            unreadable_policy = FakeContext()
            response = await handler(unreadable_policy, "route task")
            if (
                unreadable_policy.injections
                or unreadable_policy.request.request_context is not None
            ):
                raise AssertionError("unreadable policy did not fail closed")
            assert_bounded_denial(response, [str(missing_path)])
            enforced_policy_denials += 1

            policy_path.write_text(
                json.dumps(
                    {
                        "schema_version": "0.1.0",
                        "profile": "invalid-policy",
                        "allowed_tools": ["vyane_dispatch"],
                        "allow_failover": True,
                    },
                ),
                encoding="utf-8",
            )
            os.environ["VYANE_PAW_POLICY"] = str(policy_path)
            invalid_policy = FakeContext()
            response = await handler(invalid_policy, "dispatch task")
            if (
                invalid_policy.injections
                or invalid_policy.request.request_context is not None
            ):
                raise AssertionError("schema-invalid policy did not fail closed")
            assert_bounded_denial(response, [str(policy_path)])
            enforced_policy_denials += 1
    finally:
        if previous_policy is None:
            os.environ.pop("VYANE_PAW_POLICY", None)
        else:
            os.environ["VYANE_PAW_POLICY"] = previous_policy
    return enforced_policy_denials


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
    if sorted(client["tools"]) != sorted(required):
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
    runtime_contracts = assert_manifest(args.qwenpaw_architecture)
    module = load_plugin_module()
    product_contract_metrics = asyncio.run(assert_command_contract(module))
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
                "pinned_runtime_contracts": runtime_contracts,
                **product_contract_metrics,
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
