# Security and data handling

## Threat boundary

Vyane Paw can connect a conversational agent to model providers, coding-agent
harnesses, local processes, and evidence stores. Configuration mistakes can
therefore expose credentials, private prompts, filesystem data, or execution
authority.

## Rules

1. Credentials are supplied only through the deployment environment or an
   approved secret store.
2. Example files use placeholders and loopback endpoints.
3. Local configuration, runtime state, raw screenshots, traces, databases, and
   office documents remain ignored.
4. Tool exposure is allowlisted. A QwenPaw agent receives only the Vyane tools
   needed by its scenario.
5. Every evidence record identifies its sanitization state.
6. No raw prompt, model response, path, account, host, or user identifier is
   included in committed evidence.
7. A future remote gateway must add authentication, tenant isolation, replay
   protection, rate limits, audit retention, and transport security before use.

## Evidence states

- `raw`: local only and never committed.
- `sanitized`: reviewed for repository use.
- `publishable`: separately reviewed for external presentation.

## Pre-commit check

Run:

```bash
./scripts/check-repository.sh
git diff --cached
```

The script is a guardrail, not a substitute for human review.
