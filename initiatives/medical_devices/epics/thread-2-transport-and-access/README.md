# Thread 2 — Transport & Access

Same restructuring as `thread-1-data-and-keys/` (see that folder's
README for the full rationale): one file per track, each broken into
small `Session <Track>.<n>` units (one deliverable + its own tests,
sized to fit a single sitting), each with an explicit Receives/Gives/
Files-touched contract.

- [track-c-transport-authn.md](track-c-transport-authn.md) — mTLS
  transport (gRPC/REST/SOAP) + RBAC/AuthN/AuthZ (roles, sessions).
- [track-b-zmq-lifecycle.md](histories/zmq-lifecycle/track-b-zmq-lifecycle.md) — ZMQ CURVE
  security (already shipped, verify only) + full `stream[#]` lifecycle.

---

## What this whole thread receives from Foundation

- **F1** — `ComplianceContext` threaded through `main.py` and every stage.
- **F3** — `AuditSink` (no-op stub) exists and is injectable.
- **F5** — `CryptoBackend` selection seam exists — Track C's TLS stack
  links against this, not its own crypto library.
- **F4** — a tagged regression baseline exists — the diff target for
  every acceptance gate in this thread.

(F1–F5 defined in `../foundation.md`. Track B only needs F1 — see its own
file for why it doesn't consume F3/F5.)

---

## Execution order across tracks

**Track C (all sessions) before Track B (all sessions), same
session-line.** No hard *file* dependency between them — the master plan
is explicit that this ordering is "for focus, not correctness" — but keep
them together: Track C sets the credential/session model the rest of the
comm layer should stay consistent with, so building it first gives Track
B something concrete to stay consistent with rather than the reverse.

Within Track C, sessions are sequential (see that file) — mTLS before
RBAC, RBAC before token sessions. Within Track B, the CURVE-verification
step doesn't block the lifecycle sessions (no dependency either way); the
lifecycle sessions are themselves sequential.

---

## Definition of done (every session, every track in this thread)

- Unit tests for the construct/behavior that specific session introduces.
- Integration test covering end-to-end behavior in a realistic path — not
  just unit tests of a component in isolation (e.g. Track C: an actual
  mTLS handshake + RBAC-gated request over the wire).
- Full F4 regression baseline still passes.
- Sessions touching `phi`-adjacent code (Track C's whole contract, once
  the hardened floor is in place — see `harpia_medical_master_plan.md`
  §0a): one-paragraph `ComplianceReport/` note (feeds Track M later).
- No cross-variant parity gate to wait on — Track N's feature-parity diff
  was dropped entirely per §0a (one project-wide `risk_class` floor, not
  per-jurisdiction builds).
- **Ground Rule 6 (`../foundation.md`, added 2026-08-23):** any session
  that touches a consumer-facing template/adapter emits/updates accurate
  Doxygen doc-comments for what it touched, in the same session — not
  deferred. Add a row to `initiatives/doxygen-generation/doxygen-generation.md` §4 if the work
  surfaces a pitfall not already listed there.

## Watch for (thread-wide)

- Don't run Track C and Track B as separate concurrent session-lines even
  though they're logically independent — kept sequential on purpose so
  the credential model stays consistent, not because of a file conflict.
- The message-versioning effort (shipped, since deleted from `initiatives/` —
  see `HttpCapabilityAdapter/CLAUDE.md`) discovered that Track C's
  session/login mechanism does **not** exist in the real codebase yet —
  it built a standalone capability-handshake mechanism for REST/SOAP
  instead of piggybacking on a Track C session, since Track C hadn't
  shipped. Worth knowing before starting Track C: once Track C's real
  session model exists, there may be an opportunity (not an obligation)
  to reconcile with `HttpCapabilityAdapter`'s standalone mechanism — not
  scoped here, just flagged so it isn't rediscovered from scratch.
