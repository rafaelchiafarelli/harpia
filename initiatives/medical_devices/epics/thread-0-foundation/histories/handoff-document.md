## Handoff — what you're giving the other four threads (five, since Thread 5 was added 2026-08-21)

Once this merges, every other thread can assume, without re-deriving it:

- `ComplianceContext` is threaded through every stage — read the active
  profile, don't reinvent config parsing.
- `field.is_phi` exists on every parsed field — check it, don't re-parse
  the grammar.
- `AuditSink` (no-op) exists and can be injected — call it, don't build
  your own audit mechanism.
- `CryptoBackend` selection seam exists — link against it if your track
  touches TLS or key material, don't pick your own crypto library.
- A tagged green baseline (F4) exists — diff your acceptance tests against
  it, not against an arbitrary earlier commit.
- The `doxygen` target/test (F6) exists — your track doesn't build this
  machinery, it just has to keep feeding it accurate doc-comments per
  Ground Rule 6, or the gated test catches the gap.

Point the five thread folders (`thread-1-data-and-keys/` through
`thread-5-device-interop/`) at this commit/tag once merged.
