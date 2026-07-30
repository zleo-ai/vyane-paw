# MCP compatibility

## Baseline

The first proof uses the revisions in `upstreams.lock.json`:

- QwenPaw `ebb5b24d0b2559af51d71a38547d88d384357a64` and its Python MCP
  client with a stateful initialization lifecycle.
- `vyane-rs` at `319b9da521e3242b482dff46cf92f676b5f38686`.
- Rust SDK `rmcp` `3.0.1`.
- stdio transport.

`rmcp` 3.x is an enabling upgrade, not proof that every MCP 2026-07-28 feature is
implemented by Vyane Paw.

## Verified compatibility boundary

The direct stdio connection passed locally and in self-hosted CI on 2026-07-30
at the pinned revisions. The QwenPaw client completed its stateful
initialization lifecycle against the `rmcp` 3.0 server, discovered the exact
nine-tool surface, completed one safe call, received a structured
invalid-argument response, and closed cleanly.

The executable smoke test is `scripts/run-vp01.sh`. It loads the pinned,
unmodified QwenPaw `StdIOStatefulClient` module with QwenPaw-compatible Python
MCP dependency constraints, launches the pinned Vyane binary, asserts the exact
tool set, performs one safe call and one invalid-argument call, then verifies
clean lifecycle shutdown. It intentionally does not claim full QwenPaw
application integration.

The sanitized baseline is `evidence/vp01-baseline.json`. VP-01 is complete
after self-hosted CI and an independent GLM-5.2 review through the official GLM
Coding Plan both passed.

The smoke reads the resolved `rmcp` version from the pinned `vyane-rs`
`Cargo.lock` and rejects any mismatch with `upstreams.lock.json`. Python
compatibility dependencies are exact fixture versions rather than production
application constraints.

## Stable and candidate lanes

The compatibility boundary now has two deliberately different lanes:

- `scripts/run-vp01.sh` is the required stable gate. It uses only the exact
  revisions in `upstreams.lock.json` and produces reproducible evidence.
- `scripts/run-vp06.sh` is a moving candidate canary. It resolves public
  vyane-rs `main`, freezes that individual run to the resolved commit, and
  records the actual commit in ignored runtime evidence.
- `scripts/run-vp08.sh stable` proves the real durable workflow lifecycle
  against the stable lock. `scripts/run-vp08.sh candidate` runs the same
  lifecycle against the candidate checkout after its isolated probe.
- `scripts/run-vp09.sh` is the stable capability-negotiation probe. It records
  what the pinned endpoints advertise and negotiate
  (`evidence/vp09-capabilities.json`) without claiming any MCP extension as a
  product feature.

The candidate checkout and evidence path are isolated from the stable lane.
Its CI job is visible but advisory: an upstream candidate failure must not
rewrite the last proven stable claim. Promoting a candidate requires updating
the stable lock and completing the required CI and independent review gates.
The same canary is scheduled for 06:20 Asia/Shanghai and supports manual
dispatch; GitHub schedules are best-effort, while an executed scheduled run
fails visibly when current upstream `main` breaks the boundary.

Candidate source is same-owner but moving code and is therefore never executed
directly on the persistent self-hosted runner. The runner builds a digest-pinned
Rust/uv image from `compat/candidate.Dockerfile`, then runs the candidate build
and smoke inside a read-only, capability-dropped container with no Docker
socket and no persisted checkout credential. The container sees a read-only
`git archive` of tracked Vyane Paw files rather than the checkout or its ignored
runtime data, plus one per-job temporary runtime directory read-write. A
candidate job must not receive production secrets or mount other host data.
Only credential-free public proxy variables may cross the boundary; host
`NO_PROXY` values are not forwarded because they can reveal internal domains,
and the container receives loopback-only bypasses instead. Network access is
required to resolve and build the public candidate, while the fixed Rust
toolchain is intentionally read-only: a new upstream toolchain requirement is a
visible compatibility failure rather than an implicit runtime installation.
System package versions are resolved when the disposable canary image is built;
they are not part of the stable compatibility claim.

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
| `server/discover` | Explore | VP-09 probe recorded method-not-found (`-32601`) at the pinned revisions |
| MRTR routing metadata | Explore | design note and prototype |
| Custom Vyane durable workflow tools | VP-08 complete | real submit/status/cancel lifecycle through pinned QwenPaw |
| MCP Tasks extension | Deferred until negotiated | VP-09 probe recorded no `tasks` advertisement at the pinned revisions; capability probe and future bounded work package |

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
