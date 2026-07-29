# MCP compatibility

## Baseline

The first proof uses the revisions in `upstreams.lock.json`:

- QwenPaw `ebb5b24d0b2559af51d71a38547d88d384357a64` and its Python MCP
  client with a stateful initialization lifecycle.
- `vyane-rs` at `4848ec4f9d0b740fd8dc5f5586bc30111dc3d373`.
- Rust SDK `rmcp` `3.0.0`.
- stdio transport.

`rmcp` 3.0 is an enabling upgrade, not proof that every MCP 2026-07-28 feature is
implemented by Vyane Paw.

## Compatibility hypothesis

The direct connection is expected to work because the server SDK keeps legacy
initialization compatibility while adding the 2026-07-28 protocol surface.
VP-01 must prove this across the real Python client and Rust server. No document
may label the pair compatible until that test passes at pinned revisions.

## Validation matrix

| Capability | Phase 1 expectation | Evidence |
| --- | --- | --- |
| Process launch and clean shutdown | Required | exit status and bounded log |
| Legacy initialize handshake | Required | sanitized transcript |
| Tool discovery | Required | expected tool-name set |
| One tool call | Required | request/result fixture |
| Error propagation | Required | deterministic negative fixture |
| Concurrent calls | VP-02 | timing and result fixture |
| Streamable HTTP | Deferred | architecture decision |
| Stateless request handling | Deferred | protocol test |
| `server/discover` | Explore | capability probe |
| MRTR routing metadata | Explore | design note and prototype |
| Tasks extension | Final-phase candidate | durable workflow prototype |

## Upgrade impact

Moving `vyane-rs` from `rmcp` 0.5 to 3.0 should not force a Vyane Paw redesign.
It improves the long-term protocol baseline, but it raises the importance of:

- pinning exact SDK and server revisions;
- testing both legacy initialization and modern stateless behavior;
- separating protocol capability from product-level implementation;
- tracking deprecated roots, sampling, logging, and legacy SSE assumptions;
- treating authorization and request metadata as explicit policy inputs.

Primary references:

- [MCP 2026-07-28 overview](https://claude.com/blog/bringing-mcp-2026-07-28-to-claude)
- [Rust SDK rmcp 3.0 release](https://github.com/modelcontextprotocol/rust-sdk/releases/tag/rmcp-v3.0.0)
- [QwenPaw source](https://github.com/agentscope-ai/QwenPaw)
