# 0003: Cancellation remains owned by the MCP client SDK

- Status: accepted for the MVP
- Date: 2026-07-29

## Context

The pinned integration uses QwenPaw's unmodified `StdIOStatefulClient` and MCP
Python SDK 1.29.0. Cancelling the QwenPaw `call_tool` coroutine ends the local
await, but the client does not send `notifications/cancelled`. The Vyane server
therefore completes the already-issued run.

The repository's hermetic cancellation probe records this behavior with
`cancellation_propagated=0`. It is the same MCP Python SDK 1.29.0 gap described
in [python-sdk issue 2507][issue-2507].

The protocol's cancellation contract requires the notification to carry the
request ID originally allocated by the sender. At the pinned revisions:

- QwenPaw calls the public `ClientSession.call_tool` API and never receives that
  request ID;
- MCP Python SDK allocates the ID inside `BaseSession.send_request`;
- QwenPaw's plugin API cannot replace MCP session construction or register a
  cancellation-aware Driver handler;
- reading `_request_id` before a call would race with concurrent requests and
  could cancel the wrong operation.

MCP Python SDK main has since merged a dispatcher-based v2 client that sends a
courtesy `notifications/cancelled` when a request is abandoned, documented in
[python-sdk PR 2838][pr-2838]. That implementation is not the pinned QwenPaw
dependency and is not yet a verified QwenPaw compatibility baseline.

## Decision

Vyane Paw will not monkey-patch QwenPaw or MCP Python SDK internals for the MVP.
It will:

1. keep finite Vyane execution timeouts as the resource bound;
2. report local stop and server-side cancellation as different states;
3. retain the hermetic regression probe;
4. add a QwenPaw-plus-MCP-Python-v2 compatibility spike when QwenPaw adopts a
   release containing the dispatcher cancellation behavior.

The product must not claim that stopping a QwenPaw turn cancelled an existing
Vyane run.

## Consequences

- Route, dispatch, failover, and broadcast remain safe to demonstrate because
  every execution mode uses a finite timeout.
- A local user stop may leave work running until its configured timeout.
- The fix belongs below the Vyane Paw plugin boundary. Upgrading the client SDK
  is preferable to maintaining a private request-ID or session fork.
- MCP task-augmented requests use their own `tasks/cancel` operation rather
  than request cancellation. A future durable-workflow experience should map to
  that lifecycle after both QwenPaw and Vyane negotiate a compatible protocol.

[issue-2507]: https://github.com/modelcontextprotocol/python-sdk/issues/2507
[pr-2838]: https://github.com/modelcontextprotocol/python-sdk/pull/2838
