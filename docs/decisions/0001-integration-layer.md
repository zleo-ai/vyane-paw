# ADR 0001: Use an independent integration repository

- Status: accepted
- Date: 2026-07-29

## Decision

Build Vyane Paw as an independent integration and productization repository.
Do not fork QwenPaw and do not move Vyane routing into this repository.

## Rationale

QwenPaw and Vyane evolve independently and already expose suitable extension
surfaces. The valuable work is compatibility, policy, packaging, experience,
tests, and evidence. Keeping these concerns separate reduces upstream drift and
preserves clear ownership.

## Consequences

- Upstream revisions must be pinned in test evidence.
- Thin adapters are preferred.
- Upstream patches, if necessary, are proposed upstream rather than accumulated
  as a private fork.
