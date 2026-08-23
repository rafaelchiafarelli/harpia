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