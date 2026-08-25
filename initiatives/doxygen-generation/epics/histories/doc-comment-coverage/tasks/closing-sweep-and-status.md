## Session D.7 — Closing sweep + §4 status update

- **Depends on:** D.1–D.6 merged, **or their Ground Rule 6 equivalents
  landed inside other medical_devices tracks** — verify each before
  starting, don't assume.
- **Deliverable:**
  - Confirm every row in `../../../../doxygen-generation.md` §4 has both
    a landed doc comment and a golden-snapshot test asserting its specific
    content (§6) — not just presence.
  - Add a "Status" column to that table recording where/when each row
    landed (which session or track, which commit).
  - Run `tests/test_doxygen_docs.py` (F6's zero-warnings gate) against
    this repo's own real generated headers for the first time — until now
    it's only been proven against a synthetic fixture
    (`../../../../../medical_devices/epics/handoff-document.md`'s F6 note).
    Fix any residual `WARN_IF_UNDOCUMENTED` warnings this surfaces.
- **Out of scope:** adding new pitfall content — that's each earlier
  session's job. This session only verifies and closes.
- **Tests:**
  - `tests/test_doxygen_docs.py`, now meaningful against real generated
    output instead of only the synthetic fixture.
