# Engineering status and handoff

Last verified: 2026-07-30

This page is the canonical starting point for an agent continuing Vyane Paw
without conversation history. Architecture decisions remain in `docs/` and
executable acceptance criteria remain in `work-packages/`; this page records
which of those plans are current.

## Current baseline

- Repository role: private integration and productization layer between
  QwenPaw and vyane-rs; it is neither an upstream fork nor a second Vyane
  implementation.
- Integration: local stdio MCP through QwenPaw's governed MCP driver.
- Stable upstream revisions: use the exact values in `upstreams.lock.json`.
- Stable product surface:
  - request-bound route, automatic dispatch, named-profile failover, and
    bounded multi-model review;
  - durable workflow submit, status, and cancel through explicit Vyane workflow
    tools.
- Latest completed package: VP-09.
- Verified main commit:
  `a87cfc737624bd8ef6aefeff565ffcca1c9281e8`.

## Work-package ledger

| Package | State | Result |
| --- | --- | --- |
| VP-01 | Complete and merged | Pinned QwenPaw-to-vyane-rs stdio compatibility |
| VP-02 | Complete and merged | Synthetic route, failover, timeout, cancellation-gap, and broadcast flows |
| VP-03 | Complete and merged | Policy-bounded QwenPaw plugin and launcher product entry |
| VP-04 | Deferred | Competition submission evidence; not an engineering priority |
| VP-05 | Superseded and deferred | Original productization outline split into later packages; installation work is not current scope |
| VP-06 | Complete and merged | Isolated moving-candidate compatibility canary |
| VP-07 | Complete and merged | Real pinned headless QwenPaw application integration |
| VP-08 | Complete and merged | Explicit durable workflow submit/status/cancel lifecycle |
| VP-09 | Complete and merged | Stable MCP capability-negotiation probe (advertised/negotiated/product-claimed separation) |

## Verified closeout

VP-09 implementation commit
`f9bbdcf35a122cc786c44ec4ed7e7195665130e3` passed all five jobs in GitHub
Actions run `30505303139`. Official GLM-5.2 independent review run `d2b1130c`
returned `CLEAN` with no P0/P1 findings. The merge SHA of PR #9 is recorded
in the pull-request history.

VP-08 implementation commit
`454e9fd713a98063a3e50ab4542f80a0f94b9547` passed all four self-hosted jobs in
GitHub Actions run `30477535425`. Official GLM-5.2 follow-up review
`224657eb` returned `CLEAN` with no P0/P1 findings.

The final pull-request head
`3c9409ddb21aee9ebb8b6906ff17ecb1f7023306` received a clean documentation-delta
review (`670d71c0`). PR #7 merged as
`a87cfc737624bd8ef6aefeff565ffcca1c9281e8`; all four jobs on merge-SHA run
`30478848464` passed.

These identifiers are historical evidence, not a substitute for rerunning
checks after a new change.

## Current priorities

Feature work on the middleware takes precedence. A new engineering increment
must start with a new scoped work package containing goal, dependencies,
non-goals, acceptance criteria, verification commands, and required evidence.
Do not silently reopen VP-04 or VP-05 as the next feature.

The following work is explicitly deferred until requested:

- installation, upgrade, rollback, and end-user packaging;
- screenshots, recording, and competition-submission production;
- full bilingual README editorial expansion beyond keeping facts aligned;
- publishing a Vyane Paw section on `docs.zleo.ai`;
- a remote gateway;
- claiming MCP Tasks support before both pinned endpoints negotiate and pass it.

## Continuation procedure

1. Read `AGENTS.md`, this page, `docs/ARCHITECTURE.md`, and the relevant work
   package.
2. Fetch the remote and branch from the current `origin/main`; do not continue
   an already-merged feature branch.
3. Confirm `upstreams.lock.json` before making compatibility claims. The moving
   candidate lane is advisory and does not replace the stable lock.
4. Add or update one bounded work package before feature implementation.
5. Keep credentials and private deployment context outside the repository.
6. Run `scripts/check-repository.sh` and the work-package-specific gate.
7. Obtain independent cross-model review for the exact implementation head
   before merge.

## Semantic guardrails

- Stopping a request-bound QwenPaw turn is not proof that its server-side run
  was cancelled.
- VP-08 workflow cancellation is an explicit product lifecycle over custom
  Vyane workflow tools. It is not MCP request cancellation and is not an
  implementation of the MCP Tasks extension.
- The local resident Vyane daemon used by durable workflows does not by itself
  justify a new network gateway.
