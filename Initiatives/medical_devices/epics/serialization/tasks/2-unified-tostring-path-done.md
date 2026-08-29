## Session F.2 — Unified `toString` path across JSON/XML/YAML

- **Depends on:** F.1 merged.
- **Deliverable:** JSON, XML, and the new YAML adapter share one
  `toString` code path instead of three independent ones.
- **Guarantees:** `toString` never crashes, never omits structure, for
  any of the three formats.
- **Tests:**
  - Integration: round-trip a non-`phi` message through all three
    formats via the unified path.
- **Acceptance gate:** existing JSON/XML golden snapshots (14.5/14.6)
  unchanged for non-`phi` messages — this refactor must be behavior-
  preserving for the two existing formats.
