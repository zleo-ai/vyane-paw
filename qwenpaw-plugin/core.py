# -*- coding: utf-8 -*-
"""Runtime policy primitives for the Vyane Paw integration boundary."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


POLICY_ENV = "VYANE_PAW_POLICY"
POLICY_SCHEMA_VERSION = "0.1.0"
PRODUCT_TOOLS = frozenset(
    {
        "vyane_route",
        "vyane_dispatch",
        "vyane_broadcast",
    },
)
_PROFILE_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
_TOOL_FOR_MODE = {
    "route": "vyane_route",
    "dispatch": "vyane_dispatch",
    "failover": "vyane_dispatch",
    "review": "vyane_broadcast",
}


class PolicyError(ValueError):
    """A bounded, user-safe runtime policy error."""


def required_tool(plan: Mapping[str, Any]) -> str:
    """Return the sole product tool that may be exposed for this command."""
    tool = _TOOL_FOR_MODE.get(plan.get("mode"))
    if tool is None:
        raise PolicyError("命令未绑定有效的 Vyane 工具。")
    return tool


def _profile_name(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _PROFILE_NAME.fullmatch(value):
        raise PolicyError(f"{field} 必须是有效的 profile 名。")
    return value


def _strict_bool(payload: Mapping[str, Any], field: str, default: bool) -> bool:
    value = payload.get(field, default)
    if not isinstance(value, bool):
        raise PolicyError(f"策略字段 {field} 必须是布尔值。")
    return value


@dataclass(frozen=True)
class RuntimePolicy:
    """Validated policy applied before a Vyane tool can be selected."""

    schema_version: str
    profile: str
    allowed_tools: frozenset[str]
    allow_failover: bool
    allow_broadcast: bool
    max_parallel_targets: int
    allowed_targets: frozenset[str] | None

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "RuntimePolicy":
        if not isinstance(payload, Mapping):
            raise PolicyError("策略根节点必须是对象。")

        known_fields = {
            "schema_version",
            "profile",
            "allowed_tools",
            "allow_failover",
            "allow_broadcast",
            "max_parallel_targets",
            "allowed_targets",
        }
        unknown = sorted(set(payload) - known_fields)
        if unknown:
            raise PolicyError("策略包含不支持的字段。")

        version = payload.get("schema_version")
        if version != POLICY_SCHEMA_VERSION:
            raise PolicyError("策略版本不受支持。")
        profile = _profile_name(payload.get("profile"), "profile")

        raw_tools = payload.get("allowed_tools")
        if not isinstance(raw_tools, list) or not raw_tools:
            raise PolicyError("allowed_tools 必须是非空数组。")
        if any(not isinstance(tool, str) for tool in raw_tools):
            raise PolicyError("allowed_tools 只能包含字符串。")
        if len(set(raw_tools)) != len(raw_tools):
            raise PolicyError("allowed_tools 不能包含重复项。")
        tools = frozenset(raw_tools)
        if not tools.issubset(PRODUCT_TOOLS):
            raise PolicyError("策略包含非 Vyane Paw 产品工具。")

        raw_max = payload.get("max_parallel_targets", 1)
        if isinstance(raw_max, bool) or not isinstance(raw_max, int):
            raise PolicyError("max_parallel_targets 必须是整数。")
        if not 1 <= raw_max <= 4:
            raise PolicyError("max_parallel_targets 必须在 1 到 4 之间。")

        allow_failover = _strict_bool(payload, "allow_failover", False)
        allow_broadcast = _strict_bool(payload, "allow_broadcast", False)
        raw_targets = payload.get("allowed_targets")
        targets: frozenset[str] | None
        if raw_targets is None:
            targets = None
        else:
            if not isinstance(raw_targets, list):
                raise PolicyError("allowed_targets 必须是数组。")
            validated = [
                _profile_name(target, "allowed_targets") for target in raw_targets
            ]
            if len(set(validated)) != len(validated):
                raise PolicyError("allowed_targets 不能包含重复项。")
            targets = frozenset(validated)

        if allow_failover and "vyane_dispatch" not in tools:
            raise PolicyError("启用失败切换时必须授权 vyane_dispatch。")
        if allow_broadcast and "vyane_broadcast" not in tools:
            raise PolicyError("启用多目标评审时必须授权 vyane_broadcast。")
        if (allow_failover or allow_broadcast) and not targets:
            raise PolicyError("显式目标能力必须配置非空 allowed_targets。")
        if allow_broadcast and raw_max < 2:
            raise PolicyError("启用多目标评审时并行目标上限不能小于 2。")

        return cls(
            schema_version=version,
            profile=profile,
            allowed_tools=tools,
            allow_failover=allow_failover,
            allow_broadcast=allow_broadcast,
            max_parallel_targets=raw_max,
            allowed_targets=targets,
        )

    def authorize(self, plan: Mapping[str, Any]) -> None:
        """Fail closed unless the parsed command is allowed by this policy."""
        mode = plan.get("mode")
        tool = required_tool(plan)
        if tool not in self.allowed_tools:
            raise PolicyError("当前策略未授权该 Vyane 工具。")
        if mode == "failover" and not self.allow_failover:
            raise PolicyError("当前策略未授权失败切换。")
        if mode == "review":
            if not self.allow_broadcast:
                raise PolicyError("当前策略未授权多目标评审。")
            targets = str(plan.get("targets", "")).split(",")
            if len(targets) > self.max_parallel_targets:
                raise PolicyError("评审目标数量超过策略上限。")
        else:
            target = plan.get("target")
            targets = [target] if isinstance(target, str) else []

        if self.allowed_targets is not None:
            denied = [
                target for target in targets if target not in self.allowed_targets
            ]
            if denied:
                raise PolicyError("目标 profile 未被当前策略授权。")


_DEFAULT_POLICY = RuntimePolicy.from_mapping(
    {
        "schema_version": POLICY_SCHEMA_VERSION,
        "profile": "local-safe",
        "allowed_tools": ["vyane_route", "vyane_dispatch"],
        "allow_failover": False,
        "allow_broadcast": False,
        "max_parallel_targets": 1,
        "allowed_targets": [],
    },
)


def load_runtime_policy() -> RuntimePolicy:
    """Load a deployment-owned policy, or use the bounded local default."""
    configured = os.environ.get(POLICY_ENV)
    if not configured:
        return _DEFAULT_POLICY

    try:
        raw = Path(configured).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise PolicyError("无法读取已配置的 Vyane Paw 策略。") from exc
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PolicyError("已配置的 Vyane Paw 策略不是有效 JSON。") from exc
    return RuntimePolicy.from_mapping(payload)
