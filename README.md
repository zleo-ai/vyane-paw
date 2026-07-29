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

## Start today

1. Run the completed `VP-01` pinned stdio compatibility gate.
2. Run the hermetic `VP-02` route, failover, and broadcast fixtures.
3. Close the verified QwenPaw cancellation-propagation gap before claiming
   server-side cancellation from the product integration.

See [README.zh-CN.md](README.zh-CN.md) for the Chinese overview.
