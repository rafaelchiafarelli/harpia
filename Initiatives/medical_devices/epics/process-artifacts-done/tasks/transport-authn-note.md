## `ComplianceReport/` note for the transport-authn epic (mTLS + RBAC + sessions + cert provisioning + ZAP allowlist)

- **Depends on:** the sbom-emission task merged (`ComplianceReport/` module
  exists).
- **Origin:** raised by the transport-authn epic
  (`../../transport-authn/`), its final task (`full-acceptance-gate-note`).
  The epic hardens every transport a `phi`- or `critical`-bearing message can
  cross (master plan §0a — once `risk_class` implies medical-device grade the
  hardened path is the project-wide floor, not a per-message opt-in), so it is
  `phi`-adjacent by the effort's definition of done and owes a traceability
  note — but `ComplianceReport/` is the process-artifacts epic's module, not
  the transport-authn epic's, so the note is written here (same as
  `dds-transport-note.md` / `events-callbacks-phi-audit-note.md` /
  `serialization-redaction-note.md`).
- **Deliverable:** a one-paragraph `ComplianceReport/` note covering the
  transport-authn epic — what changed, why, and which tests cover it — as raw
  material for the traceability matrix:

  - **Cert provisioning (task 1).** `Assets/cmake/mtls_provision.sh` (sibling
    of `dds_security_provision.sh`, one layer less throwaway) mints, at
    configure time behind `-DUSE_MTLS`, a root CA (the trust anchor for both
    server- and client-cert verification), a server cert/key for the
    `crow::SimpleApp` / gRPC listener, and one client cert/key **per named
    identity** whose subject CommonName *is* the RBAC principal — so RBAC
    (task 4) and the ZAP allowlist read identities from a real PKI, not a demo
    keypair. Key type / curve / digest come from
    `CryptoBackend.transport_security()`, so mTLS and DDS-Security cannot land
    on different crypto modules. Dev/bootstrap posture: a local CA, not an
    enterprise-CA / HSM integration (that stays a pluggable follow-up, the same
    boundary `KeyProvider` keeps). `openssl` absent → non-zero exit, no partial
    output.

  - **mTLS on gRPC (task 2).** `Database/runtime/harpia_grpc_mtls.h` (copied
    verbatim into `generated/cpp/grpc/`): `harpia::grpc_transport::{MtlsFiles,
    SecurityRefused, server_credentials, channel_credentials}` —
    `server_credentials(hardening, files)` builds `SslServerCredentials` with
    `GRPC_SSL_REQUEST_AND_REQUIRE_CLIENT_CERTIFICATE_AND_VERIFY`, an incomplete
    `MtlsFiles` **throws** (never a silent insecure downgrade), non-hardened →
    `InsecureServerCredentials()`. The task also *built* the missing
    project-wide bring-up: `generated/cpp/grpc/grpc_server_bringup.h` (rendered
    — `#include`s every `<name>_grpc.h`, bakes `kHardeningRequired` from
    `transport_hardening_required(compliance)`, defines
    `harpia::grpc_transport::GrpcServer` = one `ServerBuilder`, every service
    registered, `BuildAndStart()`), plus `grpc/grpc_server_selection.json`
    recording the F5 `CryptoBackend` choice (same field set as
    `dds_security_selection.json`). `GrpcServiceAdapter` now takes
    `crypto_backend=` like `DdsAdapter`.

  - **mTLS on REST + SOAP together (task 3).** They share one
    `crow::SimpleApp`, so one bring-up. `Database/runtime/harpia_http_mtls.h`
    (copied verbatim into `generated/cpp/http/`):
    `make_server_context(hardening, files)` → an `asio::ssl::context`
    (`tls_server`, this server's cert/key, `load_verify_file(ca)`,
    `verify_peer | verify_fail_if_no_peer_cert` — crow's own `ssl_file()` only
    sets `verify_client_once`, which lets a **certless** client through);
    incomplete `files` throws. `generated/cpp/http/http_server_bringup.h`
    (rendered — `harpia::http_transport::HttpServer`, every `register_<name>`
    under `rest_base` and `register_<name>_soap` under `soap_base` (they must
    differ — both bind a POST on `<base>/<name>`), `app_.ssl(...)` when
    hardened) with a **`static_assert`** refusing to compile a hardened project
    without `-DCROW_ENABLE_SSL` — no silent plaintext server. Two in-task
    fixes: REST/SOAP separate base paths, and a latent
    `harpia::json::is_valid_json` ODR clash (made an overload keyed on the
    message type; single-header callers unchanged).

  - **RBAC role model (task 4).** The per-route / per-RPC gate now has two
    generation-time variants, chosen by
    `Crypto.backend.transport_hardening_required(compliance)` (`risk_class ==
    CLASS_C` or `topology == CLOUD_CONNECTED`, §0a — the *same* predicate as
    mTLS, one implementation per project, never per-jurisdiction): the flat
    `X-User`/`X-Pswd` (REST) / `<credentials>` (SOAP) / `x-user`/`x-pswd`
    metadata (gRPC) credential unchanged for non-hardened profiles, and an
    `admin` / `main` / `guest` role check for hardened. Mechanism: hand-written
    `Compliance/runtime/harpia_rbac.h` (copied verbatim into
    `generated/cpp/{http,grpc}/`) — `Role`, `Operation`, the fixed
    `permitted()` matrix (**admin** = all, **main** = all but `remove`,
    **guest** = read / list / stream, **heartBeat** open to everyone),
    `RoleMap::from_env()`, and `decide(cn, op, subject) →
    {allow, unauthenticated, forbidden}`. Identity is the verified client-cert
    subject CN — REST/SOAP from `crow::request::client_cert_cn` (a `[harpia
    patch]` to vendored crow), gRPC from `ServerContext::auth_context()`. The
    CN → role binding is read once at startup from the **`HARPIA_RBAC_MAP`**
    file (`CN role` per line) — **deployment configuration, not schema, not a
    compiled-in list** (the same reasoning that keeps the mTLS certificates out
    of the build). Fail-safe: no map file → every data operation is
    `forbidden`, `heartBeat` alone stays open. Differentiated **401 /
    UNAUTHENTICATED** (no / unverifiable identity) vs **403 / PERMISSION_DENIED**
    (valid identity, wrong role); exactly one value-free `AuditSink`
    `"rbac_denied"` record per non-allow (CN / role / operation / decision
    metadata, never a credential — design-rules Rule 5). Two task-4 follow-ons
    also landed: **`rbac-generated-tests`** (`TestAdapter` branches its
    gate-touching body builders on the same predicate, so a hardened project's
    own `-DHARPIA_BUILD_TESTS=ON` suite compiles and is fail-closed — the flat
    variant stays byte-identical) and **`zmq-zap-allowlist`** (below).

  - **Token-based sessions with expiry / revocation (task 5).** Layered on the
    RBAC gate, hardened variant only. Hand-written
    `Compliance/runtime/harpia_session.h` (`harpia::session`, copied verbatim
    into `generated/cpp/{http,grpc}/` next to `harpia_rbac.h`): a caller that
    has authenticated the mTLS transport obtains a signed bearer token
    (`v1.<b64url payload>.<mac>`, payload = CN + RBAC role + issued-at + expiry
    + a random `jti`) and presents it as `Authorization: Bearer <token>` /
    `authorization` metadata on subsequent calls **in place of re-deriving the
    identity from the certificate each time**. Every RBAC gate consults the
    token first: a token that verifies (signature + expiry + revocation)
    supplies the CN `decide()` runs on; a token that is *presented but does not
    verify* is refused outright (401 / UNAUTHENTICATED), **never** a silent
    fall-through to the certificate. Signing is real HMAC-SHA256 over a
    self-contained SHA-256 bundled in the header (checked against FIPS-180-4 /
    RFC-4231 vectors) — deliberately not an OpenSSL call, so the header stays
    pure-std and links anywhere `harpia_rbac.h` does; *which* crypto module a
    project is validated against is still recorded by the F5 seam in
    `{http,grpc}_server_selection.json`. Configuration is deployment config
    read once from the environment — `HARPIA_SESSION_KEY` (empty ⇒ sessions
    disabled: `issue()` → `""`, `verify()` → `no_key`, a fail-safe),
    `HARPIA_SESSION_TTL` (default 900 s), `HARPIA_SESSION_REVOCATIONS` (a file
    of revoked `jti`, re-read whenever its contents change so a revocation
    takes effect without a restart) — the same posture as `HARPIA_RBAC_MAP`.
    Issuance: REST `POST <rest_base>/session` (JSON) and SOAP
    `POST <soap_base>/session` (`<sessionToken>` envelope) spliced into
    `http_server_bringup.h`'s `register_session()`; gRPC `heartBeat` mints a
    `harpia-session-token` trailing-metadata value when the call carries
    `harpia-issue-session` metadata. Exactly one value-free `AuditSink`
    `"session_denied"` record per non-ok verify (verdict / CN / `jti`
    metadata, never the token bytes — Rule 5).

  - **ZMQ CURVE ZAP client-key allowlist (absorbed from `zmq-lifecycle`
    2026-08-29, scoped once task 4's identity store was real).** The shipped
    CURVE transport is encryption-only — any client with valid CURVE crypto is
    accepted. This adds the identity layer: hardened `CURVE_SERVER` sockets
    (the generated PULL receiver / PUB publisher / `<name>_stream`) call
    `::harpia::zap::ensure_running(ctx)` (a lazily-started, per-`zmq::context_t`
    `REP` handler on `inproc://zeromq.zap.01`, background thread joined on
    context shutdown — the same lazy-static technique as
    `harpia::rbac::role_map()`), which checks each client public key against the
    **`HARPIA_ZMQ_ALLOWLIST`** file (`<z85-key> <identity>` per line — the
    *same* startup-read-deployment-config shape as `HARPIA_RBAC_MAP`; the
    `identity` correlates a key to the RBAC principal for the audit trail, ZAP
    authorizes on the key). Fail-safe: hardened + no allowlist file (or an
    empty one) → **every** client key is denied at the handshake, never "allow
    all". One value-free `AuditSink` `"zap_denied"` record per rejection (z85
    key + identity metadata, never secret key material — Rule 5).
    `ZmqAdapter/runtime/harpia_zap.h`, `Assets/cmake/zmq_zap_provision.sh`.

  - **F5 `CryptoBackend` seam (Foundation, consumed here).** The mTLS stack and
    the ZAP allowlist do not pick their own crypto module — they read
    `CryptoBackend.transport_security()` (`cmake_package` / `openssl_provider` /
    `fips`) and default their hardening on off the module-level
    `transport_hardening_required(compliance)` predicate, the same rule
    `get_backend()` keys its FIPS default off, so mTLS, DDS-Security and the
    ZAP allowlist cannot diverge on *when* hardening is mandatory or *which*
    module is in play. Each transport records its selection in a
    `*_server_selection.json` / `*_selection.json` sidecar.

  - **Additive, not a replacement (acceptance gate).** The hardened path is
    gated on `transport_hardening_required(compliance)` at generation time — a
    non-hardened profile emits the flat credential gate, plaintext listeners
    and no ZAP handler, **byte-identical** to the pre-epic output. Verified end
    to end in Docker: the existing plaintext ZMQ / gRPC / REST / SOAP demo and
    round-trip tests still pass under a low-risk profile
    (`test_stage11_soap.py` / `test_stage12_rest.py` / `test_stage13.py` /
    `test_stage13_zmq.py` / `test_demo.py`); and with hardening on, across all
    three HTTP-family transports, a call with **no client certificate is
    refused at the transport** (TLS handshake), a call with a valid certificate
    bound to the **wrong role gets 403 / PERMISSION_DENIED**, and a valid
    certificate with the **correct role succeeds** (`test_rbac.py`,
    `test_sessions.py`). Full regression suite green in Docker: **462 passed,
    4 skipped**.

  - **Tests:** `UnitTests/test_mtls_provision.py` (task 1 — CA + server + per-
    identity client certs; `openssl verify` against the CA; client CN == the
    identity argument; key params track
    `CryptoBackend.transport_security()`; `openssl` absent → clean non-zero
    exit), `UnitTests/test_grpc_mtls.py` (task 2 — the generated `GrpcServer`
    over real mTLS: certless call refused at the handshake, task-1 client cert
    connects; `SecurityRefused` on incomplete PEMs; selection JSON tracks the
    F5 choice), `UnitTests/test_rest_soap_mtls.py` (task 3 — the generated
    `HttpServer` over real HTTPS, same refuse-certless / accept-with-cert on
    both REST and SOAP; the `static_assert` fires without `-DCROW_ENABLE_SSL`),
    `UnitTests/test_rbac.py` (task 4 — the fixed role×operation matrix as an
    allow/deny table, the 401/403 decision mapping, exactly one audit record
    per denial (metadata only); integration: the generated `HttpServer` /
    `GrpcServer` over real mTLS — an admin cert served every verb, a guest cert
    served reads but 403'd on writes, a valid-but-unmapped cert 403'd, no
    client cert refused at the handshake, an in-process unauthenticated gRPC
    call `UNAUTHENTICATED`), `UnitTests/test_stage14.py` (`rbac-generated-tests`
    — both gate variants' generated `<name>_test.cpp` compile and pass; the
    hardened one proves the gate is compiled in and fail-closed),
    `UnitTests/test_zmq_zap.py` (`zmq-zap-allowlist` — the ZAP handler rejects a
    client whose key isn't on the allowlist even with valid CURVE crypto,
    accepts one that is; deny-all with no file; one `zap_denied` record per
    rejection; `test_stage13_zmq` pinned low-risk for the encryption-only
    path), `UnitTests/test_sessions.py` (task 5 — issue / verify round trip and
    the role in a token matches the issuing identity; an expired token
    rejected; a revoked token rejected and the list re-read on change; a
    tampered / malformed / no-key token rejected; exactly one `session_denied`
    record per non-ok verdict with no token bytes in the detail; integration
    REST + SOAP + gRPC over real mTLS — a token issued on one call is accepted
    on the next, an admin token used from a guest client cert still gets the
    admin verbs, an expired or revoked token is 401 / UNAUTHENTICATED),
    `UnitTests/test_crypto_backend.py` (the F5 seam: `transport_security()`
    tracks the backend, `transport_hardening_required()` follows
    `risk_class` / `topology`),
    `UnitTests/test_golden.py` (the `rest/` `soap/` `grpc/` `http/` `gen_tests/`
    snapshots + the new `{http,grpc}/harpia_rbac.h` / `harpia_session.h` and
    `zap/` runtimes).

- **Fold into `ComplianceReport/requirements.py`:** deferred to a
  **process-artifacts** task, not done here. The current matrix builder
  (`ComplianceReport/ComplianceReport.py::_traceability_rows`) has `applies_to`
  values `phi_field` / `phi_field_table` / `critical_message` / `project` only
  — none of which is scoped to "a transport-hardening obligation" or "a project
  under a hardened compliance profile". Adding mTLS / RBAC / session / ZAP rows
  correctly needs a new `applies_to` (e.g. `hardened_transport`, keyed off
  `transport_hardening_required(compliance)`) plus a change to
  `_traceability_rows()` (which also moves the `compliancereport/` golden) —
  that is the process-artifacts epic's module and its call, exactly the reason
  `ComplianceReport/` notes are filed as process-artifacts tasks
  (`epics/README.md` DoD rule 6). This file is the raw material for that task,
  the same carve-out `dds-transport-note.md` took pending a `dds`-scoped
  `applies_to`.

- **Tests:** covered by the matrix spot-check once the fold-in task above runs
  (one row per annotated construct).

---
## Epic context — process-artifacts

**Contract.** SBOM (CycloneDX/SPDX), a traceability matrix, jurisdiction-selected
doc templates (fda/eu_mdr/anvisa), and the `ComplianceReport/` module every
`phi`-adjacent epic writes a one-paragraph note into. This is the one place
`jurisdiction[]` actually drives different output. Needs `ComplianceContext` from
Foundation. Terminal artifact — feeds the regulatory submission, not another epic
(except versioning, which extends the `ComplianceReport/` output once
sbom-emission has merged).

**Files.** New `ComplianceReport/` module.

**Watch for.** Before considering this epic done: check the `ComplianceReport/`
notes from db-encryption, transport-authn, events-callbacks / serialization, and
dds-transport actually landed — the matrix is only as complete as those notes.
