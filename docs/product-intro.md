# Vyane Paw — product introduction (unpublished draft)

> **Status: content preparation only.** This page is sanitized and
> self-contained, but it has NOT been published and must not leave the
> repository until the owner completes an explicit disclosure review
> (repository is private; see `AGENTS.md`). All names, paths, and examples
> are synthetic placeholders.

Vyane Paw is the integration product that connects a QwenPaw agent workspace
to Vyane's multi-model execution. QwenPaw remains the conversation, channel,
memory, and plugin host; Vyane remains the routing, dispatch, broadcast,
failover, and durable-workflow authority. Vyane Paw packages the seam into
repeatable product flows with policy guardrails and reproducible evidence.

## What a user gets

- One `/vyane` command inside QwenPaw with bounded product modes:
  deterministic route preview, automatic dispatch, named-profile failover,
  bounded multi-model review, and an explicit durable workflow lifecycle
  (submit / status / cancel).
- A local stdio MCP connection launched through a small launcher; no extra
  network listener and no permanent gateway.
- Deployment-owned policy: a JSON policy document decides which tools,
  targets, and modes are available; credentials never enter the product
  repository.

## How it stays honest

- Compatibility is claimed only at exact pinned upstream revisions, recorded
  in a lock file; a moving candidate canary watches upstream and is advisory
  only.
- Every claimed capability is backed by schema-validated, committed evidence
  and a gate script that reproduces it.
- The product explicitly does not claim MCP Tasks support, remote transports,
  server discovery, or server-side cancellation from stopping a chat turn.
  Durable workflow cancellation is a separate, explicit lifecycle.

## 中文摘要

Vyane Paw 把 QwenPaw 的 Agent 工作区与 Vyane 的多模型执行连成一条受策略
约束、证据可复验的产品路径：一个 `/vyane` 命令提供路由预览、自动分发、
失败切换、并行评审和持久工作流生命周期；本机 stdio MCP 直连，不建网关；
兼容性只按钉版 revision 声称；不声称 MCP Tasks、远程传输或服务端取消。

## Current state

The verified capability set covers pinned stdio compatibility, synthetic
routing/failover/timeout/broadcast flows, a policy-bounded plugin entry, a
real headless application integration, the durable workflow lifecycle, and a
capability-negotiation probe. Installation and end-user packaging are
intentionally deferred.
