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

## Verified compatibility boundary

The direct stdio connection passed locally on 2026-07-29 at the pinned
revisions. The QwenPaw client completed its stateful initialization lifecycle
against the `rmcp` 3.0 server, discovered the exact nine-tool surface, completed
one safe call, received a structured invalid-argument response, and closed
cleanly.

The executable smoke test is `scripts/run-vp01.sh`. It loads the pinned,
unmodified QwenPaw `StdIOStatefulClient` module with QwenPaw-compatible Python
MCP dependency constraints, launches the pinned Vyane binary, asserts the exact
tool set, performs one safe call and one invalid-argument call, then verifies
clean lifecycle shutdown. It intentionally does not claim full QwenPaw
application integration.

The sanitized baseline is `evidence/vp01-baseline.json`. CI and independent
review remain required before VP-01 is marked complete.

The smoke reads the resolved `rmcp` version from the pinned `vyane-rs`
`Cargo.lock` and rejects any mismatch with `upstreams.lock.json`. Python
compatibility dependencies are exact fixture versions rather than production
application constraints.

## Validation matrix

| Capability | Phase 1 expectation | Evidence |
| --- | --- | --- |
| Process launch and clean shutdown | Required | exit code and reaped-process assertion |
| Legacy initialize handshake | Required | completed pinned-client smoke |
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
