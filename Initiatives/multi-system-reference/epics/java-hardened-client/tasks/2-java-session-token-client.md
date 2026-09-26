## Java session-token client (issue, attach, refresh)

- **Depends on:** task 1.
- **Contract:** runtime class `com.harpia.runtime.HarpiaSession`:
  `static HarpiaSession issue(Channel ch)` calls the generated `heartBeat` with
  `harpia-issue-session` metadata and reads the `harpia-session-token`
  trailing metadata. It exposes `ClientInterceptor interceptor()`, which
  attaches `authorization: Bearer <token>` to every call, and it re-issues the
  token when a call fails with `UNAUTHENTICATED` because it expired
  (`HARPIA_SESSION_TTL`). Re-issue happens once per failure, never in a loop.
  This mirrors the C++ server's protocol exactly as documented in `USAGE.md` §8.
- **Pre-work:** none.
- **Out of scope:** revocation handling beyond surfacing the error; REST/SOAP
  `POST /session` (Java REST/SOAP clients are an initiative non-goal).
- **Tests:** JDK-gated pytest against the hardened C++ `GrpcServer` with
  `HARPIA_SESSION_KEY` set: token issued; a call with the token under a `guest`
  CN can `list` but gets `PERMISSION_DENIED` on `create`; a short TTL (2s)
  makes the interceptor re-issue exactly once; a garbage token is refused
  (`UNAUTHENTICATED`) and is not silently replaced by the cert identity.
