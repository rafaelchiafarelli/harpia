## Bearer session tokens, byte-compatible with C++ `harpia_session.h`

- **Depends on:** task 6.
- **Contract:**
  - `harpia_runtime/session.py`, a port of
    `Compliance/runtime/harpia_session.h`:
    - `Claims`, `Verdict`;
    - `issue(cn, role, ttl, now)` produces `v1.<b64url(payload)>.<hmac
      hex>`, with payload `cn\nrole\niat\nexp\njti` and a 128-bit jti
      from `secrets`;
    - `verify(token, now, sink)` checks signature (`hmac.compare_digest`),
      expiry and revocation, and records one `session_denied` per non-ok
      (never token bytes);
    - `from_authorization("Bearer …")`.
  - Config: `HARPIA_SESSION_KEY` (raw or `@path`; empty disables
    sessions), `HARPIA_SESSION_TTL` (default 900),
    `HARPIA_SESSION_REVOCATIONS` (re-read when the **content hash**
    changes, lock-guarded).
  - Issuance:
    - REST/SOAP: `POST <base>/session` routes, same request/response shape
      as C++ `register_session()`;
    - gRPC: `heartBeat` with `harpia-issue-session` metadata returns a
      `harpia-session-token` trailing-metadata value.
  - Acceptance:
    - every RBAC gate first tries `Authorization: Bearer` / `authorization`
      metadata;
    - a **presented but invalid** token is refused (401 /
      `UNAUTHENTICATED`) and never falls through to the cert.
  - A client helper for Python callers: obtain a token, then attach it.
- **Bar:** a token issued by a C++ server verifies on a Python server with
  the same key, and vice versa (the format is the contract).
- **Out of scope:** OAuth/OIDC.
- **Tests:**
  - Generated-project tests mirroring `test_sessions.py`: issue, use,
    expire, revoke, tamper, presented-invalid-no-fallthrough.
  - HMAC/SHA-256 vector checks (RFC 4231).
  - A g++-gated cross-verification in both directions.
