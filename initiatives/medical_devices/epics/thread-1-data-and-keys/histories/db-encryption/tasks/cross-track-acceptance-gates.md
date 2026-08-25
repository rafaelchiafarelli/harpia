## Session A.4 — Full round-trip + cross-track acceptance gates

- **Depends on:** A.1–A.3 merged.
- **Deliverable:** nothing new to build — this session closes out the
  integration tests that could only be proven once Track A's DAO
  genuinely exists (deferred from Track O's O.5, not droppable):
  - Track O's KEK-rotation round trip: write → persist → rotate KEK →
    read both pre- and post-rotation data, confirming no full-database
    re-encryption occurred.
  - Track O's backend-swap proof: swap `KeyProvider` backend (O.2's
    default → O.5's reference adapter) with zero changes to this track's
    generated DAO code.
- **Acceptance gate:** existing non-`phi` CRUDL golden tests (14.1/14.2)
  unchanged.
