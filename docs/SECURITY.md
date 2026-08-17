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

## CI runner trust boundary

- This public repository has no self-hosted workflow. Pull requests, pushes,
  schedules, and manual checks all run on the explicit GitHub-hosted runner
  allowlist.
- `pull_request_target`, `workflow_run`, `repository_dispatch`, reusable
  workflow jobs, dynamic runner expressions, and custom runner labels are
  rejected by the repository checker.
- A lightweight local runner, if retained, belongs to a separate private
  control repository. It must fetch an explicitly trusted revision and cannot
  be a fallback or required check for this public repository.
- Hosted setup actions run without cache upload so untrusted pull-request data
  is not persisted as a repository cache.
- `scripts/check_workflow_trust_boundary.py` enforces this boundary as part of
  `scripts/check-repository.sh`.

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
