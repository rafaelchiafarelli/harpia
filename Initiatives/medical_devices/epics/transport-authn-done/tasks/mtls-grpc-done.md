## mTLS on gRPC

Scoped 2026-08-30. **Task 2** of the transport-authn epic. No dependency on
task 3 — the two mTLS tasks may run in parallel on separate session-lines.

**Scope expanded 2026-08-30 (Rafael's call).** The original scope assumed a
generated gRPC server bring-up existed to wire `SslServerCredentials` into. It
did not — `GrpcServiceAdapter` emitted only the header-only per-message
`harpia::grpc_svc::<name>_service` impls; the consumer supplied their own
`grpc::ServerBuilder` (`Database/CLAUDE.md`'s "TLS is caller-side" note, now
updated). Rather than split, this task now also *builds* that bring-up.

- **Depends on:** task 1 (`cert-provisioning`) merged; F1, F3, F5 (Foundation).
- **Deliverable (as built):**
  - `Database/runtime/harpia_grpc_mtls.h` — hand-written credentials mechanism,
    copied verbatim into `generated/cpp/grpc/` (same pattern as
    `harpia_dds_security.h`). `harpia::grpc_transport::MtlsFiles`,
    `SecurityRefused`, `server_credentials(hardening, files)` →
    `SslServerCredentials` with
    `GRPC_SSL_REQUEST_AND_REQUIRE_CLIENT_CERTIFICATE_AND_VERIFY` (incomplete
    `files` throws — never a silent insecure downgrade), else
    `InsecureServerCredentials()`; `channel_credentials(...)` symmetric for the
    client.
  - `generated/cpp/grpc/grpc_server_bringup.h` — rendered from
    `Database/templates/grpc_server_bringup.h.tmpl`: `#include`s every
    `<name>_grpc.h`, bakes `inline constexpr bool kHardeningRequired` from
    `Crypto.backend.transport_hardening_required(compliance)`, and defines
    `harpia::grpc_transport::GrpcServer` — one `ServerBuilder`, every generated
    service registered, `AddListeningPort(addr, server_credentials(...))`,
    `BuildAndStart()`. A no-address overload builds an in-process-only server.
  - `generated/cpp/grpc/grpc_server_selection.json` — the F5 `CryptoBackend`
    choice + `hardening_required`, same field set as
    `dds_security_selection.json`. `GrpcServiceAdapter` now takes
    `crypto_backend=` (wired from `main.py` / `run_pipeline.py`) like
    `DdsAdapter`; path constants in `Compliance/grpc_common.py`.
  - Cert / key / CA paths are the caller's to pass (`MtlsFiles`); the
    `USE_MTLS` build flag from task 1 emits a `harpia_mtls_files.h` with them.
- **Guarantees:** `kHardeningRequired` true → a gRPC call over the generated
  `GrpcServer` with no client cert fails at the TLS handshake, a call with a
  task-1 client cert connects; the per-RPC `authorized()` x-user/x-pswd metadata
  check in each `<name>_grpc.h` is untouched and still runs on top. False →
  `InsecureServerCredentials()`, per-message output byte-identical to before
  (only the `grpc_service.h.tmpl` header doc-comment moved).
- **Out of scope:** replacing the credential-metadata gate with RBAC (task 4);
  REST / SOAP (task 3); sessions (task 5); a generated gRPC *demo main* (the
  bring-up is a reusable runner, not a binary).
- **Tests (`UnitTests/test_grpc_mtls.py`):**
  - Structural: the three files ship; the bring-up `#include`s + registers every
    service; `kHardeningRequired` / the selection record follow the compliance
    profile (flip verified by direct-driving `GrpcServiceAdapter` with a
    CLASS_A / STANDALONE context); no bring-up emitted without a table message.
  - Integration (Docker toolchain): `harpia_grpc_mtls.h` compiles standalone
    and its fail-safe holds; a live gRPC call over a real TCP socket through the
    generated `GrpcServer` — accepted with a task-1 client cert, refused for an
    insecure client.
  - Golden: `test_golden.py` regenerated — `grpc/` gains the three files, the 12
    `*_grpc.h` move by the header doc-comment only, `.proto` and service method
    signatures unchanged. `test_golden_java.py` untouched (C++-only change; its
    pre-existing `telemetry` drift is a separate fix branch).
- **Doc-comments:** `grpc_service.h.tmpl` header block points at the bring-up;
  `harpia_grpc_mtls.h` + `grpc_server_bringup.h.tmpl` carry full header prose;
  `Database/CLAUDE.md`'s "TLS is caller-side" gotcha + `GrpcServiceAdapter.py`
  bullet updated.

---
## Epic context — transport-authn

**Contract.** mTLS on all three HTTP-family transports (gRPC / REST / SOAP),
admin/main/guest RBAC replacing the flat `X-User`/`X-Pswd` gate, token-based
sessions with expiry/revocation, and cert provisioning scripts — plus a ZMQ
CURVE ZAP client-key allowlist (absorbed from zmq-lifecycle 2026-08-29). One
implementation per project, compiled in and gated by `risk_class`, never
per-jurisdiction (`harpia_medical_master_plan.md` §0a). Needs `ComplianceContext`
(F1), the `AuditSink` stub (F3), and the `CryptoBackend` seam (F5) from
Foundation — the TLS stack links the F5 seam's `transport_security()` /
`transport_hardening_required()`, it does not pick its own crypto module.

**Files.** `Assets/` (cert provisioning scripts + `CMakeLists.txt` / `vcpkg.json`
wiring); `Database/templates/{rest,soap,grpc_service}.h.tmpl` and their emitters
`Database/{RestAdapter,SoapAdapter,GrpcServiceAdapter}.py` (the credential gate —
`authorized_{name}()` helper + the 401 / UNAUTHENTICATED check at each route);
the generated server bring-up glue that instantiates `crow::SimpleApp` /
`grpc::ServerBuilder` (`Assets/server_template/`, `main.py` glue) for the TLS
listener config; `ZmqAdapter/` for the absorbed ZAP-allowlist work.

**Ordering (within the epic).** cert-provisioning → mTLS (gRPC ∥ REST/SOAP) →
RBAC → sessions → acceptance-gate note. Auth sits on top of an authenticated
transport, not the other way around. mtls-grpc and mtls-rest-soap have no
dependency on each other and may run on two session-lines; do not reorder them
ahead of cert-provisioning or after RBAC.

**Not scoped as a task yet.** The ZMQ CURVE ZAP allowlist stays a documented
deliverable, not a numbered task, until task 4's identity store is real — the
allowlist must read from *that* store, not invent its own
(`transport-authn/README.md`, "Watch for"). Scope it after task 4. The
`HttpCapabilityAdapter/` session mechanism (a standalone REST/SOAP path shipped
by the message-versioning effort) is an opportunity to reconcile with task 5's
real session model, not an obligation.

**Decision to confirm (provisioning posture).** Task 1 is scoped as a local
CA + leaf-issuance tool (root CA, server cert, per-identity client certs with
subject CN = the RBAC principal) in dev/bootstrap posture — real enough to be
the identity source RBAC (task 4) and the ZAP allowlist build on, but not an
integration with an external enterprise CA / HSM (that stays a pluggable
follow-up, same boundary `KeyProvider` keeps). Flagged for Rafael; revisit
task 1's scope if that reading is wrong.
