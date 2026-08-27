## Session K.1 — Registry + access-check implementation

- **Depends on:** F1 (Foundation), Track A (A.1–A.4) merged.
- **Deliverable:** environment-level registry distinguishing public vs.
  private databases per project.
- **Guarantees:** a private table is inaccessible cross-project; a public
  table remains accessible to any project with library access.
- **Tests:**
  - Unit: access-check denies cross-project private access.
  - Integration: two projects — one queries the other's public table
    (succeeds) and private table (denied).
- **Acceptance gate:** existing single-project tests unaffected.
