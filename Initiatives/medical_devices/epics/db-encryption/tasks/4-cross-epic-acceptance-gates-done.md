## Full round-trip + cross-epic acceptance gates

- **Depends on:** task 1–task 3 merged.
- **Deliverable:** nothing new to build — this session closes out the
  integration tests that could only be proven once the db-encryption epic's DAO
  genuinely exists (deferred from the key-management epic's kms-hsm-reference-adapter task, not droppable):
  - the key-management epic's KEK-rotation round trip: write → persist → rotate KEK →
    read both pre- and post-rotation data, confirming no full-database
    re-encryption occurred.
  - the key-management epic's backend-swap proof: swap `KeyProvider` backend (the default-local-provider task's
    default → its reference adapter) with zero changes to this epic's
    generated DAO code.
- **Acceptance gate:** existing non-`phi` CRUDL golden tests (14.1/14.2)
  unchanged.
