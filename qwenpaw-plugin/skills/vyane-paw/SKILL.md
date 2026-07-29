---
name: vyane-paw
description: Route, dispatch, fail over, or review through the Vyane MCP boundary.
---

# Vyane Paw

Use this Skill when the user invokes `/vyane` or explicitly asks QwenPaw to
route, dispatch with failover, or obtain a bounded multi-model review through
Vyane.

## Product flows

- Route preview: call `vyane_route`. State explicitly that routing preview does
  not execute the task.
- One-target execution: call `vyane_dispatch`. A named profile may contain a
  configured failover chain.
- Multi-model review: call `vyane_broadcast` once with two to four explicit,
  comma-separated targets. Preserve target order and each target's independent
  outcome.

## Result contract

- Treat `operation_status="completed"` as terminal even when
  `detail_omitted=true`; do not retry it as a failure.
- Present partial broadcast success and failed targets separately.
- Distinguish an MCP transport failure, policy denial, timeout, recorded
  execution failure, and bounded completed receipt.
- Do not claim server-side cancellation when only the local QwenPaw turn was
  stopped. The pinned QwenPaw client does not currently propagate local
  coroutine cancellation as MCP `notifications/cancelled`.
- Never print secrets, absolute paths, endpoint URLs, environment names, raw
  provider errors, or hidden reasoning.
- Never substitute a different provider, model, local shell command, or the
  current QwenPaw model when the selected Vyane operation is unavailable.

## Safe defaults

- Use `allow_frontier=false` for automatic routing unless the user explicitly
  authorizes frontier use.
- Use `sandbox="read_only"` for harness targets unless a more permissive
  sandbox is explicitly required and authorized.
- Use a finite timeout for execution and broadcast.
- Do not attach a work directory unless the task genuinely requires a harness
  and the user has placed that directory in scope.
