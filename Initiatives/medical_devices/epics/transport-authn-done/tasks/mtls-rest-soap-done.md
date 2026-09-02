## mTLS on REST/SOAP

Scoped 2026-08-30. **Task 3** of the transport-authn epic. REST and SOAP
together, not two efforts — they share one `crow::SimpleApp`. No dependency on
task 2.

**Scope expanded 2026-08-30 — same shape as task 2's expansion.** There was no
generated Crow server bring-up to wire TLS into (`Database/CLAUDE.md`'s "TLS is
caller-side" note); this task builds one, mirroring task 2's gRPC bring-up.
Crow's `ssl(asio::ssl::context&&)` overload takes it cleanly — no vendored
patch, so the "Watch for" stop condition did not trigger. Two second-order
findings, both handled in-task:
  1. **REST + SOAP cannot share the same base path** — both bind a POST route
     on `<base>/<name>` (crow throws "handler already exists"). The bring-up
     mounts them under separate bases (`rest_base` / `soap_base`, default
     `""` / `"/soap"`).
  2. **`harpia::json::is_valid_json` was a latent ODR clash** — a non-overloaded
     free function, one per message, identical signature. Including every
     `<name>_rest.h` in one TU (which the bring-up does) redefined it. Fixed in
     `JsonAdapter/templates/adapter.h.tmpl` with a trailing defaulted `const
     {cls}*` so it becomes an overload keyed on the message type; every
     existing single-header caller (`is_valid_json(js)`) resolves unchanged via
     the default argument. Moves the `json/` golden (comment + the extra param).

- **Depends on:** task 1 (`cert-provisioning`) merged; F1, F3, F5 (Foundation).
- **Deliverable (as built):**
  - `Database/runtime/harpia_http_mtls.h` — hand-written, copied verbatim into
    `generated/cpp/http/`. `harpia::http_transport::{MtlsFiles, SecurityRefused}`
    and `make_server_context(hardening, files)` → an `asio::ssl::context`
    (`tls_server`, this server's cert/key, `load_verify_file(ca)`, and
    `verify_peer | verify_fail_if_no_peer_cert` — crow's own `ssl_file()` only
    sets `verify_client_once`, which lets a certless client through). Incomplete
    `files` throws — never a plaintext / no-verify server.
  - `generated/cpp/http/http_server_bringup.h` — rendered from
    `Database/templates/http_server_bringup.h.tmpl`: `#include`s every
    `<name>_rest.h` + `<name>_soap.h`, defines
    `harpia::http_transport::HttpServer` — one `crow::SimpleApp`, every
    `register_<name>` under `rest_base` and `register_<name>_soap` under
    `soap_base`, and (when `kHardeningRequired`) `app_.ssl(make_server_context(
    ...))`. A `static_assert` refuses to compile a hardened project without
    `-DCROW_ENABLE_SSL` — the compile-time fail-safe.
  - `generated/cpp/http/http_server_selection.json` — F5 `CryptoBackend` choice
    + `hardening_required`, same field set as `dds_security_selection.json` /
    `grpc_server_selection.json`. `RestAdapter` now takes `crypto_backend=`
    (wired from `main.py` / `run_pipeline.py`); it enumerates the same
    table-message set `SoapAdapter` does, so it emits the combined bring-up.
    Path constants in `Compliance/http_common.py`.
  - The per-route `authorized_{name}` / `<credentials>` checks are untouched —
    mTLS sits under them.
- **Guarantees:** `kHardeningRequired` true → an HTTPS request through the
  generated `HttpServer` with no client cert is refused at the TLS handshake, a
  request with a task-1 client cert reaches the credential gate. False →
  plain HTTP, per-message route output byte-identical (only the
  `rest.h.tmpl` / `soap.h.tmpl` header doc-comment moved).
- **Out of scope:** RBAC (task 4); gRPC (task 2); sessions (task 5); reconciling
  the `HttpCapabilityAdapter/` standalone path (task 5's optional concern); a
  generated HTTP demo binary.
- **Tests (`UnitTests/test_rest_soap_mtls.py`):**
  - Structural: the three files ship; the bring-up `#include`s + registers every
    REST + SOAP route on `rest_base` / `soap_base`; `kHardeningRequired` / the
    selection record follow the compliance profile (flip verified by
    direct-driving `RestAdapter` with a CLASS_A / STANDALONE context); no
    bring-up without a table message.
  - Integration (Docker toolchain): `harpia_http_mtls.h` compiles against
    crow/asio + OpenSSL and its fail-safe holds; a live HTTPS request against
    the generated `HttpServer` over a real socket — 200 with a task-1 client
    cert + credentials, TLS handshake refused with no client cert.
  - Golden: `test_golden.py` regenerated (`test_http_server_bringup` added) —
    new `http/` dir; the 12 `*_rest.h` + 12 `*_soap.h` move by the header
    doc-comment only; `json/` moves by the `is_valid_json` overload param.
    `test_golden_java.py` untouched.
- **Doc-comments:** `rest.h.tmpl` / `soap.h.tmpl` header blocks point at the
  bring-up; `harpia_http_mtls.h` + `http_server_bringup.h.tmpl` carry full
  header prose; `Database/CLAUDE.md`'s "TLS is caller-side" gotcha +
  `RestAdapter.py` bullet updated.

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
