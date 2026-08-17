# Engineering status and handoff

Last verified: 2026-08-17

This page is the canonical starting point for an agent continuing Vyane Paw
without conversation history. Architecture decisions remain in `docs/` and
executable acceptance criteria remain in `work-packages/`; this page records
which of those plans are current.

## Current baseline

- Repository role: public integration and productization layer between QwenPaw
  and vyane-rs; it is neither an upstream fork nor a second Vyane
  implementation. Public CI is restricted to GitHub-hosted runners by VP-16.
- Integration: local stdio MCP through QwenPaw's governed MCP driver.
- Stable upstream revisions: use the exact values in `upstreams.lock.json`.
- Stable product surface:
  - request-bound route, automatic dispatch, named-profile failover, and
    bounded multi-model review;
  - durable workflow submit, status, and cancel through explicit Vyane workflow
    tools;
  - durable workflow submit/status/cancel **and** succeeded bounded output
    retrieval (`output` / `output_omitted`) on pin `03dbd2fd` (VP-15).
- Latest completed package: VP-16.
- Verified main commit:
  `65a31e38614629a923ccaa396afe53a7f2f972fd`.

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
| VP-10 | Complete and merged | Stable upstream lock promotion to vyane-rs `319b9da` / rmcp `3.0.1` |
| VP-11 | Complete and merged | Product documentation introduction (bilingual README, docs.zleo.ai content preparation) |
| VP-12 | Complete and merged | Cancellation-propagation adoption spike and advisory upstream canary |
| VP-13 | Complete and merged | Durable-workflow control-plane readiness gate (intermittent CI failure) |
| VP-14 | Complete and merged | Durable readiness budget and failure self-diagnosis |
| VP-15 | Complete and merged | WP-152 pin `03dbd2fd`; result_contract + dual bound; hermetic run-vp08 with `terminal_succeeded_with_output == 1` (PR #22) |
| VP-16 | Complete and merged | Public workflows use hosted-only CI; repository runner registration removed after PR/main evidence |

## Verified closeout

VP-16 closeout on 2026-08-17: all public workflow jobs use the exact
`ubuntu-24.04` allowlist, and the fail-closed trust-boundary checker rejects
self-hosted/custom runners, dynamic expressions, dangerous events, and reusable
workflow jobs. Final implementation head
`04c901a7cfafc4cc11edd38273355fb728e08e78` passed independent review and all
five jobs in pull-request run `31998140166`. PR #24 merged as
`65a31e38614629a923ccaa396afe53a7f2f972fd`; all five jobs passed again in
merged-main run `31999107556`. Operator-recorded sequence: after confirming
that run had passed, the offline `rog-wsl-vyane-paw` runner (ID `2`) was
deleted; a subsequent repository runner API query reported `total_count: 0`.

VP-15 phase two closeout on 2026-08-01: hermetic `scripts/run-vp08.sh`
against lock pin `03dbd2fd1f1a3f7d6d7f8aa9396c6ce55b5d22f0` returned
`result == "passed"` with `metrics.terminal_succeeded_with_output == 1`
(cancel lifecycle plus submit → succeeded → bounded answer retrieval).
`scripts/check-repository.sh` green. Merged as PR #22
(`ae45844509ba519da9c6fe4c9e7b6c7bfb2b4c2c`); independent reviews Kimi Code
`b344132e`/`1672b4fa` and K3 `509e260f`/`80fb573f`; CI run `30705266697` green
after one durable SQLite-busy flake rerun.

VP-14 implementation commit
`a920719f179702f14a623f5c54fe68bb25892b34` passed all five jobs in GitHub
Actions run `30527863205`. Official GLM-5.2 independent review run `d501904d`
returned `CLEAN` with no P0/P1 findings; its P2 wording observation was
closed in the same pull request, and the follow-up delta review run
`fc42b4d8` returned `CLEAN`. PR #19 merged as
`4b2aa49e344b302220466853f2ae8d38bd16c2fd`; all five jobs on merge-SHA run
`30529704738` passed.

VP-13 implementation commit
`8b0d7f20816a4d28c967c453781232a099abf4d0` passed the stable CI lanes in
GitHub Actions run `30524569341`. Official GLM-5.2 independent review run
`3730f9b5` returned `CLEAN` with no P0/P1 findings; its P2/P3 observations
were closed in the same pull request, and the follow-up delta review run
`b8b28bbc` returned `CLEAN`. PR #17 merged as
`91d50494c340a04473467f4f4d53cbc7118f4df0`; all five jobs on merge-SHA run
`30525921843` passed.

VP-12 implementation commit
`689d77659a9453cf98a97227e5eb775999d56013` passed the CI lanes in GitHub
Actions run `30516885260`. Official GLM-5.2 independent review run `62dfe298`
returned `CLEAN` with no P0/P1 findings; its P2/P3 observations on the
adoption-canary edge cases were closed in the same pull request, and the
follow-up delta review run `1a64ec70` returned `CLEAN`. PR #15 merged as
`3d3840355ec8dc8bbcdd2bb59c1df328d08d483a`; all five jobs on merge-SHA run
`30517834436` passed.

VP-11 implementation commit
`418a557781450e36295143003d5a89ffdb37e65e` passed the stable CI lanes in
GitHub Actions run `30514141954`. Official GLM-5.2 independent documentation
review run `366bd16c` returned `CLEAN` with no P0/P1 findings; its P2
observation on evidence wording was closed in the same pull request, and the
final documentation-delta review run `421bf692` returned `CLEAN`. PR #13
merged as `0ef0cd60db5b43699573baf3e2dca8c7d73fc4cb`; all five jobs on
merge-SHA run `30515181118` passed.

VP-10 implementation commit
`8f7edc16d864a408dfca1f748a82e127bff42ea4` passed all five jobs in GitHub
Actions run `30508741435`; the advisory candidate canary returned to green
once the lock matched upstream again. Official GLM-5.2 independent review run
`e46e510d` returned `CLEAN` with no P0/P1 findings; its two P2 observations
(README baseline lines, VP-02 tracked evidence) were closed in the same pull
request, and the final documentation-delta review run `75356365` returned
`CLEAN`. PR #11 merged as
`bbb603063519eafcd85161341bc1f40b8e9de7b4`; all five jobs on merge-SHA run
`30510213480` passed.

VP-09 implementation commit
`f9bbdcf35a122cc786c44ec4ed7e7195665130e3` passed all five jobs in GitHub
Actions run `30505303139`. Official GLM-5.2 independent review run `d2b1130c`
returned `CLEAN` with no P0/P1 findings; the final documentation-delta review
run `6e7d8fb9` also returned `CLEAN`. PR #9 merged as
`184b76d0d58fa41f79bb96ac0f9e24b19f5f3f4d`; all four stable-lane jobs on
merge-SHA run `30506842310` passed (the advisory candidate canary failed on an
upstream `rmcp` 3.0.1 drift signal, which does not alter the stable claim).

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

VP-16 is complete. The public repository has no registered self-hosted runner;
future lightweight local CI, if needed, must live in a separate private
control plane and cannot be a public-PR fallback or required check.

The owner approved three next directions on 2026-07-30; they are the
intended continuation order for a new agent picking up this repository:

1. **Durable-failure forensics, standing watch.** VP-14 made every
   durable-workflow CI failure dump bounded runtime-log tails. If the
   `durable-workflow` job fails again, read the tails first; only then
   decide whether a bounded daemon-connect retry belongs in vyane-rs.
   No standing change is needed while it stays green.
2. **agentscope / MCP SDK v2 adoption, standing watch.** The VP-12 canary
   (`scripts/run-vp12.sh`, advisory candidate lane) fails loudly once a
   current agentscope release allows `mcp` 2.x. When it fires, re-run the
   full ADR-0003 QwenPaw-plus-SDK-v2 spike before changing any claim.

Feature work on the middleware takes precedence otherwise. A new engineering
increment must start with a new scoped work package containing goal,
dependencies, non-goals, acceptance criteria, verification commands, and
required evidence. Do not silently reopen VP-04 or VP-05 as the next feature.

The following work is explicitly deferred until requested:

- installation, upgrade, rollback, and end-user packaging;
- screenshots, recording, and competition-submission production;
- publishing a Vyane Paw section on `docs.zleo.ai` (content prepared in
  VP-11; publishing requires an explicit owner disclosure review first);
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
