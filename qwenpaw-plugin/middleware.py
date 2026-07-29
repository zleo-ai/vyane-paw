# -*- coding: utf-8 -*-
"""QwenPaw middleware enforcing the Vyane Paw result contract."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator, Callable
from typing import TYPE_CHECKING, Any

from agentscope.middleware import MiddlewareBase

from .result_contract import (
    normalize_tool_payload,
    payload_from_text_blocks,
    protocol_failure,
)

if TYPE_CHECKING:
    from agentscope.agent import Agent


class VyaneResultContractMiddleware(MiddlewareBase):
    """Inject the turn contract and normalize its selected tool result."""

    def __init__(self, contract: dict[str, str]) -> None:
        self._contract = dict(contract)

    async def on_system_prompt(
        self,
        agent: "Agent",  # pylint: disable=unused-argument
        current_prompt: str,
    ) -> str:
        """Append the validated command contract as system-level context."""
        contract_prompt = self._contract["system_prompt"].strip()
        if not contract_prompt or contract_prompt in current_prompt:
            return current_prompt
        if current_prompt.strip():
            return f"{current_prompt.rstrip()}\n\n{contract_prompt}"
        return contract_prompt

    async def on_acting(
        self,
        agent: "Agent",  # pylint: disable=unused-argument
        input_kwargs: dict[str, Any],
        next_handler: Callable[..., AsyncGenerator[Any, None]],
    ) -> AsyncGenerator[Any, None]:
        from agentscope.message import TextBlock
        from agentscope.tool import ToolResponse

        tool_call = input_kwargs.get("tool_call")
        if getattr(tool_call, "name", None) != self._contract["exposed_tool"]:
            async for event in next_handler():
                yield event
            return

        async for event in next_handler():
            if not isinstance(event, ToolResponse):
                yield event
                continue
            payload = payload_from_text_blocks(event.content or [])
            if payload is None:
                normalized = protocol_failure(
                    tool=self._contract["tool"],
                    mode=self._contract["mode"],
                    policy_profile=self._contract["policy_profile"],
                    code="missing_structured_payload",
                )
            else:
                normalized = normalize_tool_payload(
                    tool=self._contract["tool"],
                    mode=self._contract["mode"],
                    policy_profile=self._contract["policy_profile"],
                    payload=payload,
                )
            event.content = [
                TextBlock(
                    type="text",
                    text=json.dumps(
                        normalized,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                ),
            ]
            metadata = dict(event.metadata or {})
            metadata["vyane_paw_result_schema"] = normalized["schema_version"]
            metadata["vyane_paw_operation_status"] = normalized["operation_status"]
            event.metadata = metadata
            yield event
