# Vyane Paw

Vyane Paw is the private integration and productization layer between
[QwenPaw](https://github.com/agentscope-ai/QwenPaw) and
[vyane-rs](https://github.com/zleo-ai/vyane-rs).

It combines QwenPaw's user-facing agent workspace, channels, memory, and plugin
surface with Vyane's multi-model routing, dispatch, broadcast, failover, and
workflow execution. It is intentionally not a QwenPaw fork and not a second
Vyane implementation.

## Current decision

- Product name: **Vyane Paw**
- Repository: `vyane-paw`
- Visibility: private
- Integration strategy: MCP first, direct stdio for the first proof of concept
- Permanent gateway: deferred until remote, multi-tenant, authorization, or
  protocol-translation requirements justify it
- First compatibility baseline:
  - QwenPaw `ebb5b24d0b2559af51d71a38547d88d384357a64`
  - `vyane-rs` baseline `4848ec4f9d0b740fd8dc5f5586bc30111dc3d373`
  - `rmcp` `3.0.0`

## Repository map

- `docs/ARCHITECTURE.md` — system boundaries and target architecture
- `docs/STATUS.md` — current work-package ledger, deferred scope, and
  context-free continuation procedure
- `docs/MCP-COMPATIBILITY.md` — protocol baseline and validation matrix
- `docs/COMPETITION-PLAN.md` — delivery milestones through the initial and final
  submissions
- `docs/DEMO-SCENARIOS.md` — the product stories to demonstrate
- `docs/SECURITY.md` — data, credential, and evidence handling
- `docs/decisions/` — architecture decisions
- `work-packages/` — executable work definitions
- `config/examples/` — synthetic configuration examples
- `schemas/` — sanitized policy and evidence contracts
- `upstreams.lock.json` — exact upstream revisions used by the compatibility gate

## Product entry

The bundle under `qwenpaw-plugin/` registers one `/vyane` command with seven
product modes:

- `route` and automatic `dispatch`;
- named-profile `failover`;
- bounded multi-model `review`;
- durable `workflow-submit`, `workflow-status`, and `workflow-cancel`.

The standard QwenPaw MCP import in `config/examples/` connects this product
entry to the validated `vyane-paw-mcp` stdio launcher without putting provider
credentials in the repository. Durable controls are invoked through QwenPaw's
governed DriverManager and require separate policy authorization.

Use `scripts/run-vp03.sh` for the pinned plugin and launcher contract,
`scripts/run-vp07.sh` for the real headless QwenPaw application path, and
`scripts/run-vp08.sh` for the durable workflow lifecycle. The full current
ledger and continuation procedure are in
[docs/STATUS.md](docs/STATUS.md).

Local QwenPaw coroutine cancellation is not server-side Vyane request
cancellation at the pinned MCP Python SDK revision. Request-bound modes retain
finite execution timeouts. The separate VP-08 durable lifecycle provides
explicit workflow cancellation through custom Vyane tools; it is not the MCP
Tasks extension.

See [README.zh-CN.md](README.zh-CN.md) for the Chinese overview.
