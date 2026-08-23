### F4 — Golden-snapshot / regression baseline

**Status: done, on `feature/thread-0-foundation`, not yet merged to `main`.**
Unlike F1/F2/F3, F4 was never its own history file from the prior session --
it isn't a piece of code to build, it's the standing acceptance gate every
other task in this session diffs against. That gate already existed before
this session started (`tests/test_golden.py`, snapshots committed under
`tests/golden/`) and stayed green, unmodified, through F1 (ComplianceContext
plumbing), F2 (`phi` field modifier), and F3 (AuditSink stub) -- each of
those tasks' own commit explicitly re-ran the golden suite plus the full
Docker toolchain suite and confirmed no drift and no new failures beyond the
pre-existing, documented `third_party/asio` gap. That repeated confirmation
*is* what "F4 done" means here: there was never a separate deliverable for
this task to produce, only a baseline to keep green, and it stayed green.

This file exists only long enough to carry the same "done" marker
convention as F1/F2/F3's history files in this directory, then gets removed
-- F4 has no lasting artifact of its own to keep around (no new module, no
new interface), so there's nothing for a permanent file to document that
`tests/test_golden.py` and this session's own commit history don't already
cover.

- **Deliverables:** none beyond what already existed -- `tests/test_golden.py`
  + `tests/golden/` predate this session.
- **Guarantees:** every subsequent Foundation task's acceptance gate diffs
  against this exact baseline, not an arbitrary earlier commit.
- **Verified by:** every commit in this session (F1, F2, F3) re-ran
  `tests/test_golden.py` (host) and the full Docker toolchain suite,
  confirming zero drift in the committed snapshots and no new failures.
