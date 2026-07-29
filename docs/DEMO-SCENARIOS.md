# Demo scenarios

## 1. Best-target routing

The user submits one task in QwenPaw. Vyane selects a target using declared
capabilities and policy, returns the selected target class and result, and
records sanitized decision evidence.

Success measures:

- completion rate;
- routing decision validity;
- median end-to-end latency;
- operator interventions.

## 2. Failure-aware dispatch

The primary target fails with a deterministic synthetic error. Vyane applies an
allowed fallback and returns a result without requiring the user to restart the
conversation.

Success measures:

- fallback success rate;
- recovery latency;
- duplicate side effects;
- clarity of the surfaced failure reason.

## 3. Multi-model review

QwenPaw asks Vyane to broadcast a bounded task to multiple targets and present a
structured comparison or review result.

Success measures:

- number of independent valid responses;
- disagreement surfaced to the user;
- total latency and cost proxy;
- trace completeness after sanitization.

All demonstrations use synthetic inputs and non-sensitive repositories or
fixtures.

## Automated fixture

`scripts/run-vp02.sh` exercises all three flows through QwenPaw's pinned,
unmodified stdio MCP client and local synthetic OpenAI-compatible endpoints.
It records sanitized route, failover, failure-isolation, timeout, cancellation,
and broadcast evidence without requiring provider credentials.

The pinned QwenPaw client currently does not turn local coroutine cancellation
into an MCP `notifications/cancelled` message. Timeout is enforced and recorded
by Vyane, while local cancellation is reported as a known integration gap
rather than a completed server-side cancellation. The request ID needed for a
correct notification is allocated inside MCP Python SDK 1.29.0 and is not
exposed to QwenPaw's `call_tool` wrapper. The MVP therefore does not monkey-patch
client internals; see
[`0003-cancellation-owned-by-client-sdk.md`](decisions/0003-cancellation-owned-by-client-sdk.md).

## 4. Durable workflow control

QwenPaw submits a fixed, policy-authorized Vyane workflow, queries it by a
caller-owned UUIDv7, requests cancellation twice to prove idempotence, and
observes the terminal cancelled state.

Success measures:

- submit acceptance and outcome correlation;
- observable state progression;
- idempotent cancellation acknowledgement;
- terminal workflow cancellation;
- bounded process cleanup and absence of task text in runtime evidence.

`scripts/run-vp08.sh` executes this lifecycle through a real pinned QwenPaw
application and the stable vyane-rs baseline. This is explicit cancellation of
a custom Vyane workflow. It does not repair request-bound MCP cancellation and
does not claim the MCP Tasks extension.
