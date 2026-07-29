# Schema migrations

Vyane Paw's policy, operation-result, and evidence documents are runtime
contracts. Their `schema_version` values use semantic versioning independently
from the plugin version.

## Compatibility rules

- A patch release may clarify descriptions or tighten tests without changing
  accepted or emitted JSON.
- A minor release may add optional fields. Readers must ignore optional fields
  introduced by a newer minor release only when their enclosing schema permits
  them.
- Removing or renaming a field, changing its type or meaning, narrowing an
  accepted enum, changing a default, or making an optional field required is a
  major change.
- A breaking change must not replace the current schema in place. Add the new
  version beside it, keep the previous reader during a bounded transition, and
  provide old-input/new-output migration fixtures.
- Writers switch only after the compatibility matrix proves that the pinned
  QwenPaw and both stable and candidate vyane-rs lanes accept the new contract.
- Evidence files are immutable observations. Migration creates a new file with
  provenance; it never rewrites the original observation.

## Required change set

Before merging a breaking schema change, the same pull request must contain:

1. the new versioned schema and migration function;
2. positive fixtures for old and new versions plus negative boundary fixtures;
3. dual-read tests and an explicit writer cutover;
4. an update to `upstreams.lock.json` when an upstream contract caused the
   change;
5. sanitized compatibility evidence and independent review.

No generator may emit `sanitization_state=publishable`. That state requires a
separate human approval record containing the digest of the sanitized source.
