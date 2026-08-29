# Track K — Public/private DB segregation

Kept as one session — it's already a single, bounded deliverable with its
own tests, the same grain every other session in this thread targets; no
further split needed.

## Receives (must be done before this track starts)

- **F1** from Foundation (see `../thread-1-data-and-keys/README.md`).
- **Every session in Track A** (`track-a-db-encryption.md`, A.1–A.4)
  merged — this track shares the same `Database/` generator files Track
  A just modified, and starts immediately after in the same
  session-line.

## Gives (what "done" means here, consumed by whom)

- An environment-level registry distinguishing public vs. private
  databases per project, with access-check enforcement.
- **Consumed by:** no downstream track in this thread or documented
  elsewhere in the plan set. **Flag:** the docs don't name a consumer for
  this track's output — not inferring one.

## Files this track touches

- `Database/` (per `harpia_medical_master_plan.md` §2's track table).
  **Flag:** no specific filename is named in the plan docs for this
  track — not guessing further than the directory-level entry the docs
  give.

---

