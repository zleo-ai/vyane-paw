# Vyane Paw QwenPaw plugin

This bundle registers:

- `/vyane` as the product command;
- the `vyane-paw` Skill for result and safety handling.

It deliberately does not modify QwenPaw's internal DriverCard store. Install the
plugin while QwenPaw is offline, then import the MCP client configuration from
`config/examples/qwenpaw-mcp.example.json` in the QwenPaw Console.

```bash
qwenpaw plugin install /path/to/vyane-paw/qwenpaw-plugin
```

The separate MCP entry is intentional: QwenPaw's public plugin API supports
commands and Skill providers, while MCP clients are managed through the Console
or its MCP API.

Failover and review selectors are profile names, not arbitrary
`provider/model` selectors. They accept only letters, digits, `.`, `_`, and
`-`; this keeps user-controlled selectors out of the privileged instruction
surface. The MCP product surface contains six tools: route, dispatch,
broadcast, and the durable workflow submit/status/cancel controls. Durable
workflow commands use QwenPaw's governed DriverManager directly and require a
deployment policy that explicitly enables them and allowlists the target
profile.
