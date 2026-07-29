# AGENTS.md

## Repository role

`vyane-paw` is a private integration and productization repository connecting
QwenPaw with Vyane. It owns adapters, safe configuration examples, compatibility
tests, demo flows, evidence schemas, and delivery documentation. It does not fork
or mirror either upstream runtime.

## Safety boundary

- Never commit credentials, tokens, cookies, private endpoints, real account
  identifiers, personal information, employer information, or production data.
- Never commit original competition templates, internal screenshots, office
  documents, or unredacted runtime traces.
- All examples must use synthetic names and placeholder paths.
- Raw evidence belongs in ignored local directories. Only explicitly reviewed,
  sanitized assets may be placed under `docs/assets/sanitized/`.
- Before every commit, inspect the complete staged diff and run
  `scripts/check-repository.sh`.

## Engineering boundary

- QwenPaw remains the interaction, agent workspace, channel, memory, and plugin
  host.
- Vyane remains the model-routing, dispatch, broadcast, failover, workflow, and
  execution authority.
- This repository should prefer configuration and thin adapters over copied
  upstream code.
- Any protocol gateway requires an accepted architecture decision. Do not add a
  permanent middle service merely to bridge compatible stdio MCP endpoints.
- Pin upstream revisions in compatibility evidence. Do not claim compatibility
  from version ranges alone.

## Delivery rules

- Work starts from a scoped file in `work-packages/`.
- A work package is complete only when its acceptance criteria and evidence are
  present.
- Implementation, test, and independent review should be separated for changes
  that affect execution authority or security.
- Independent model review defaults to GLM-5.2 through an official subscription
  plan. Local profile names and credentials are deployment-specific and must
  not be committed. Do not silently substitute a relay or another model.
- Keep the repository private until the product boundary and disclosure plan
  have been reviewed explicitly.
