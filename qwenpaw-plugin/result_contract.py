# -*- coding: utf-8 -*-
"""Versioned normalization for Vyane MCP tool results."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from typing import Any


RESULT_SCHEMA_VERSION = "0.1.0"
_FINAL_OPERATION = "completed"
_SAFE_CODE = re.compile(r"^[a-z0-9_.-]{1,128}$")


def _safe_code(value: Any) -> str:
    code = str(value or "")
    return code if _SAFE_CODE.fullmatch(code) else "unknown"


def _record_outcome(record: Any) -> str:
    if not isinstance(record, Mapping):
        return "unknown"
    status = str(record.get("status") or record.get("run_status") or "").lower()
    if status in {"succeeded", "success", "completed"}:
        return "success"
    if status in {
        "error",
        "failed",
        "timed_out",
        "timeout",
        "cancelled",
        "canceled",
    }:
        return "failure"
    return "unknown"


def _broadcast_outcome(items: Any) -> str:
    if not isinstance(items, list) or not items:
        return "unknown"
    successes = 0
    failures = 0
    for item in items:
        if not isinstance(item, Mapping):
            failures += 1
        elif item.get("error") is not None:
            failures += 1
        elif item.get("record") is not None or item.get("receipt") is not None:
            outcome = _record_outcome(item.get("record") or item.get("receipt"))
            if outcome == "success":
                successes += 1
            else:
                failures += 1
        else:
            failures += 1
    if successes and failures:
        return "partial"
    if successes:
        return "success"
    return "failure"


def _completed_outcome(tool: str, payload: Mapping[str, Any]) -> str:
    if tool == "vyane_route":
        return "success"
    if tool == "vyane_broadcast":
        return _broadcast_outcome(payload.get("items"))
    return _record_outcome(payload.get("record") or payload.get("receipt"))


def normalize_tool_payload(
    *,
    tool: str,
    mode: str,
    policy_profile: str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Map a Vyane payload into the stable Vyane Paw result envelope."""
    if payload.get("status") == "error":
        error = payload.get("error")
        code = _safe_code(error.get("code") if isinstance(error, Mapping) else None)
        return {
            "schema_version": RESULT_SCHEMA_VERSION,
            "tool": tool,
            "mode": mode,
            "policy_profile": policy_profile,
            "operation_status": "rejected",
            "outcome": "failure",
            "detail_state": "not_applicable",
            "retry_guidance": "do_not_retry",
            "error": {"code": code},
        }

    if payload.get("ok") is False:
        return {
            "schema_version": RESULT_SCHEMA_VERSION,
            "tool": tool,
            "mode": mode,
            "policy_profile": policy_profile,
            "operation_status": "transport_failure",
            "outcome": "failure",
            "detail_state": "not_applicable",
            "retry_guidance": "do_not_retry",
            "error": {"code": _safe_code(payload.get("type"))},
        }

    operation_status = payload.get("operation_status")
    if tool == "vyane_route" and operation_status is None:
        operation_status = _FINAL_OPERATION
    if operation_status != _FINAL_OPERATION:
        return protocol_failure(
            tool=tool,
            mode=mode,
            policy_profile=policy_profile,
            code="unexpected_operation_status",
        )

    detail_omitted = payload.get("detail_omitted", False)
    if not isinstance(detail_omitted, bool):
        return protocol_failure(
            tool=tool,
            mode=mode,
            policy_profile=policy_profile,
            code="invalid_detail_state",
        )
    return {
        "schema_version": RESULT_SCHEMA_VERSION,
        "tool": tool,
        "mode": mode,
        "policy_profile": policy_profile,
        "operation_status": "completed",
        "outcome": _completed_outcome(tool, payload),
        "detail_state": "receipt" if detail_omitted else "full",
        "retry_guidance": "do_not_retry",
        "data": dict(payload),
    }


def protocol_failure(
    *,
    tool: str,
    mode: str,
    policy_profile: str,
    code: str,
) -> dict[str, Any]:
    """Return a bounded failure without copying an upstream raw error."""
    return {
        "schema_version": RESULT_SCHEMA_VERSION,
        "tool": tool,
        "mode": mode,
        "policy_profile": policy_profile,
        "operation_status": "protocol_failure",
        "outcome": "failure",
        "detail_state": "not_applicable",
        "retry_guidance": "do_not_retry",
        "error": {"code": code},
    }


def payload_from_text_blocks(content: Iterable[Any]) -> Mapping[str, Any] | None:
    """Select the last JSON object from an AgentScope tool response."""
    candidate: Mapping[str, Any] | None = None
    for block in content:
        text = (
            block.get("text")
            if isinstance(block, Mapping)
            else getattr(block, "text", None)
        )
        if not isinstance(text, str):
            continue
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(value, Mapping):
            candidate = value
    return candidate
