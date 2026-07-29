# Delivery plan

## Current planning status

This document preserves the competition-oriented delivery windows. Engineering
work on the middleware currently takes precedence. Installation, screenshots,
recording, submission production, and the `docs.zleo.ai` publication are
deferred until explicitly requested; they are not the next autonomous work
items. Current implementation status is tracked in
[`STATUS.md`](STATUS.md).

## Outcome

Demonstrate that an existing QwenPaw-based assistant can gain controlled
multi-model execution without replacing its user experience or agent workspace.

## Milestones

| Window | Deliverable | Exit condition |
| --- | --- | --- |
| Jul 29–31 | Protocol spike | VP-01 passes at pinned revisions |
| Aug 1–4 | Working proof of concept | Three demo scenarios run end to end |
| Aug 5–7 | Product evidence | Metrics, architecture, screenshots, limitations |
| Aug 8–10 | Initial submission freeze | Reproducible demo and reviewed document facts |
| Aug 11–25 | Productization | Plugin packaging, safe config, regression suite |
| Aug 26–Sep 10 | Durable workflow | VP-08 custom Vyane submit/status/cancel lifecycle complete; MCP Tasks remains deferred |
| Sep 11–18 | Polish | Installation, UX, reliability, final evidence |
| Sep 19–23 | Final freeze | Demo, document, code, and disclosure review complete |

## Initial submission target

The realistic target by Aug 10 is a credible integration proof, not a full
platform:

- one-click or documented local connection;
- route, dispatch/failover, and broadcast/review demonstrations;
- measurable success, latency, fallback, and operator-effort indicators;
- architecture and security boundary;
- sanitized screenshots and a short recorded backup demo.

## Final target

By the final window, aim for:

- a QwenPaw plugin or equivalent supported installation unit;
- deterministic compatibility and regression tests;
- configurable tool allowlists and policy profiles;
- structured, sanitized evidence export;
- one durable workflow capability;
- documented limitations and enterprise deployment path.

## Scope guard

Do not spend the initial phase rebuilding QwenPaw UI, Vyane routing, or a remote
gateway. Product proof and reproducibility outrank feature count.
