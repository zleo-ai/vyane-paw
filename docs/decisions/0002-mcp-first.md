# ADR 0002: Start with direct stdio MCP

- Status: accepted
- Date: 2026-07-29

## Decision

Use QwenPaw's MCP client to launch the Vyane MCP server over stdio for the first
proof of concept.

## Rationale

It is the shortest path that exercises both real implementations, adds no
network service, and directly tests the effect of the `rmcp` 3.0 upgrade.

## Consequences

- VP-01 is a cross-language compatibility gate.
- A gateway is not part of the initial submission scope.
- Remote and multi-tenant operation requires a later decision.
