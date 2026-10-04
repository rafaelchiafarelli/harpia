## gRPC + REST cross-calls, flat and hardened (mTLS, RBAC, sessions)

- **Depends on:** `py-transports-http` (all), `py-versioning` tasks 1–2.
- **Contract:**
  - Every server language (C++, Python) is called by every client language
    (C++ test client, Java, Python) over gRPC and REST:
    - flat profile: credentials accepted, wrong credentials refused;
    - hardened profile, same PKI: certless refused; `main` CN can create
      but not remove; `guest` read-only;
    - a session token issued by one server language is accepted by a
      server of the other language with the same `HARPIA_SESSION_KEY`;
    - capability `negotiate` cross-language on both transports.
  - The Java client uses the hardened client from `multi-system-reference`
    / `java-hardened-client`, if that has reached `dev` by then.
    Otherwise Java's hardened half is skipped with an explicit reason, and
    that is said in the epic report.
- **Tests:** `UnitTests/test_transport_xlang3.py` (gated as task 1).
