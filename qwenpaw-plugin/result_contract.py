# -*- coding: utf-8 -*-
"""Versioned normalization for Vyane MCP tool results."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from typing import Any


RESULT_SCHEMA_VERSION = "0.1.0"
_FINAL_OPERATION = "completed"
# Align with vyane-rs WORKFLOW_VIEW_OUTPUT_MAX_BYTES (UTF-8 bytes).
_WORKFLOW_OUTPUT_MAX_BYTES = 64 * 1024
_SAFE_CODE = re.compile(r"^[a-z0-9_.-]{1,128}$")
_UUID7 = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
)
_WORKFLOW_TOOLS = frozenset(
    {
        "vyane_workflow_submit",
        "vyane_workflow_status",
        "vyane_workflow_cancel",
    },
)
_WORKFLOW_STATES = frozenset(
    {
        "queued",
        "running",
        "cancelling",
        "succeeded",
        "failed",
        "timed_out",
        "cancelled",
        "interrupted",
    },
)


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
    unknown = 0
    for item in items:
        if not isinstance(item, Mapping):
            failures += 1
        elif item.get("error") is not None:
            failures += 1
        elif item.get("record") is not None or item.get("receipt") is not None:
            outcome = _record_outcome(item.get("record") or item.get("receipt"))
            if outcome == "success":
                successes += 1
            elif outcome == "failure":
                failures += 1
            else:
                unknown += 1
        else:
            unknown += 1
    if unknown:
        return "unknown"
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
    if tool in _WORKFLOW_TOOLS:
        state = str(payload.get("state") or "")
        if state in {"failed", "timed_out", "interrupted"}:
            return "failure"
        if state in _WORKFLOW_STATES:
            return "success"
        return "unknown"
    return _record_outcome(payload.get("record") or payload.get("receipt"))


def _select(source: Mapping[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    return {field: source[field] for field in fields if field in source}


def _project_attempt(attempt: Any) -> Any:
    if not isinstance(attempt, Mapping):
        return None
    projected = _select(
        attempt,
        ("target", "transport", "started_at", "duration_ms"),
    )
    outcome = attempt.get("outcome")
    if isinstance(outcome, Mapping):
        projected["outcome"] = _select(
            outcome,
            ("result", "kind", "failed_over"),
        )
    return projected


def _project_record(record: Any) -> Any:
    if not isinstance(record, Mapping):
        return None
    projected = _select(
        record,
        (
            "view_schema",
            "run_id",
            "started_at",
            "finished_at",
            "sandbox",
            "target",
            "transport",
            "status",
            "usage",
            "cost_usd",
            "session_attached",
            "output_chars",
            "terminal_error_kind",
        ),
    )
    attempts = record.get("attempts")
    if isinstance(attempts, list):
        projected["attempts"] = [
            item
            for attempt in attempts
            if (item := _project_attempt(attempt)) is not None
        ]
    return projected


def _project_receipt(receipt: Any) -> Any:
    if not isinstance(receipt, Mapping):
        return None
    return _select(
        receipt,
        (
            "receipt_schema",
            "run_id",
            "run_status",
            "terminal_error_kind",
            "output_chars",
        ),
    )


def _project_broadcast_item(item: Any) -> Any:
    if not isinstance(item, Mapping):
        return None
    projected = _select(
        item,
        ("index", "target", "output", "status", "output_omitted"),
    )
    record = _project_record(item.get("record"))
    if record is not None:
        projected["record"] = record
    receipt = _project_receipt(item.get("receipt"))
    if receipt is not None:
        projected["receipt"] = receipt
    error = item.get("error")
    if isinstance(error, Mapping):
        projected["error"] = {"code": _safe_code(error.get("code"))}
    return projected


def _project_completed_payload(
    tool: str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    if tool == "vyane_route":
        return _select(
            payload,
            (
                "profile",
                "provider",
                "model",
                "tier",
                "effort",
                "intent",
                "complexity_score",
                "selection_basis",
            ),
        )
    if tool in _WORKFLOW_TOOLS:
        # Additive WP-152 fields: only present on succeeded status when the
        # provider projects them; _select drops missing keys.
        projected = _select(
            payload,
            (
                "caller_id",
                "state",
                "failure_code",
                "output",
                "output_omitted",
            ),
        )
        state = str(payload.get("state") or "")
        if state != "succeeded":
            projected.pop("output", None)
            projected.pop("output_omitted", None)
            return projected
        raw_output = projected.get("output")
        if isinstance(raw_output, str):
            if len(raw_output.encode("utf-8")) > _WORKFLOW_OUTPUT_MAX_BYTES:
                projected.pop("output", None)
                projected["output_omitted"] = True
        elif "output" in projected:
            # Non-string bodies cannot be shipped as the answer field; drop them
            # and mark omission so the envelope is not silently empty.
            projected.pop("output", None)
            projected["output_omitted"] = True
        omitted = projected.get("output_omitted")
        if omitted is not None and not isinstance(omitted, bool):
            projected.pop("output_omitted", None)
            omitted = projected.get("output_omitted")
        # Trust boundary: never keep a body when the omit flag is true.
        if omitted is True:
            projected.pop("output", None)
        return projected
    projected = _select(
        payload,
        (
            "operation_status",
            "output",
            "output_omitted",
            "detail_omitted",
        ),
    )
    if tool == "vyane_dispatch":
        record = _project_record(payload.get("record"))
        if record is not None:
            projected["record"] = record
        receipt = _project_receipt(payload.get("receipt"))
        if receipt is not None:
            projected["receipt"] = receipt
        return projected
    items = payload.get("items")
    if isinstance(items, list):
        projected["items"] = [
            item
            for raw_item in items
            if (item := _project_broadcast_item(raw_item)) is not None
        ]
    return projected


def normalize_tool_payload(
    *,
    tool: str,
    mode: str,
    policy_profile: str,
    payload: Mapping[str, Any],
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Map a Vyane payload into the stable Vyane Paw result envelope."""
    if payload.get("status") == "error":
        error = payload.get("error")
        code = _safe_code(error.get("code") if isinstance(error, Mapping) else None)
        retry_guidance = (
            "check_status_before_retry"
            if tool == "vyane_workflow_submit" and code == "outcome_unknown"
            else "do_not_retry"
        )
        result = {
            "schema_version": RESULT_SCHEMA_VERSION,
            "tool": tool,
            "mode": mode,
            "policy_profile": policy_profile,
            "operation_status": "rejected",
            "outcome": "failure",
            "detail_state": "not_applicable",
            "retry_guidance": retry_guidance,
            "error": {"code": code},
        }
        if retry_guidance == "check_status_before_retry":
            if not isinstance(correlation_id, str) or not _UUID7.fullmatch(
                correlation_id,
            ):
                return protocol_failure(
                    tool=tool,
                    mode=mode,
                    policy_profile=policy_profile,
                    code="missing_correlation_id",
                )
            result["correlation"] = {"caller_id": correlation_id}
        return result

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
    if (
        tool in _WORKFLOW_TOOLS
        and operation_status is None
        and payload.get("state") in _WORKFLOW_STATES
        and isinstance(payload.get("caller_id"), str)
    ):
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
        "data": _project_completed_payload(tool, payload),
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
    """Select the most likely structured Vyane object from text blocks."""
    candidate: Mapping[str, Any] | None = None
    candidate_score = 0
    discriminator_keys = {
        "operation_status",
        "status",
        "ok",
        "profile",
        "state",
        "caller_id",
    }
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
            score = len(discriminator_keys.intersection(value))
            if score >= candidate_score and score > 0:
                candidate = value
                candidate_score = score
    return candidate
