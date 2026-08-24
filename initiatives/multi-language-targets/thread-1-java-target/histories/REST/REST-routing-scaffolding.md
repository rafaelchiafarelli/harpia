### Session J.12 — REST routing scaffolding

- **Depends on:** J.2 merged.
- **Deliverable:** routing on JDK-builtin `com.sun.net.httpserver.HttpServer`
  (zero dependency, low-level enough that harpia's generated routing code
  fills the gap the same way it does for Crow today) — recommended over a
  third-party layer like Javalin for the same "least new dependency
  surface" reasoning the XML runtime used. Credential-gate port (the
  `X-User`/`X-Pswd` check) from `Database/RestAdapter.py`.
- **Out of scope:** the CRUDL handlers themselves (J.13).
- **Tests:**
  - Unit: credential gate accepts/rejects per the same rules as the C++
    implementation.

## Implementation notes (landed 2026-08-23, together with J.13/J.14)

New `JavaRestAdapter/runtime/HttpRestHelpers.java`: the credential gate
(`authorized(exchange, user, pswd)`, parameterized rather than per-message
closures — Java doesn't need a generated function just to close over two
string literals) plus the routing-gap-filler `HttpServer` needs since it
has no `:id`-style path variables (`trailingId()`, recovering collection-
vs-item from one registered context via longest-prefix match). Full
rationale in `JavaRestAdapter/CLAUDE.md`.

Tests landed as part of `tests/test_java_rest.py` (covers J.12/J.13/J.14
together) — see J.14's own notes for why they weren't split three ways.