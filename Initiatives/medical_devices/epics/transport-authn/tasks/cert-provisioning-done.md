## Cert provisioning scripts

Scoped 2026-08-30. **Task 1** of the transport-authn epic — the shared
prerequisite for every mTLS task below. Mirrors
`Assets/cmake/dds_security_provision.sh` (the DDS-Security analogue) in shape and
location, one layer less throwaway: this one issues per-identity client certs
whose subject CN is the RBAC principal, so task 4 and the ZAP allowlist read
identities from it rather than a demo keypair.

- **Depends on:** F5 (Foundation) — the script's key/cert parameters (key type,
  curve/size, digest) come from `CryptoBackend.transport_security()`'s
  descriptor, so mTLS and DDS-Security cannot silently land on different crypto
  modules. No dependency on any other transport-authn task.
- **Deliverable:** a configure-time provisioning script in `Assets/cmake/`
  (sibling to `dds_security_provision.sh` / `curve_keygen_probe.cpp`) that mints:
  - a root CA (cert + key), the trust anchor for both server-cert and
    client-cert verification in the generated project;
  - a server cert/key (subject CN / SAN from an argument, default the project
    base path) for the `crow::SimpleApp` / gRPC listener;
  - one or more client certs/keys, subject CN = an identity name passed by the
    caller — this is the string RBAC task 4 maps to a role.

  Wired into `Assets/CMakeLists.txt` behind a build flag — name it `USE_MTLS`
  and document it here so tasks 2/3 consume the same one — and into
  `Assets/vcpkg.json` if OpenSSL is not already a listed dependency.
- **Out of scope:** wiring any cert into an actual transport listener or client
  (tasks 2 / 3); identity→role mapping (task 4); external enterprise-CA / HSM
  integration (a pluggable follow-up, the same boundary `KeyProvider` keeps for
  envelope encryption — not this epic); any change to
  `dds_security_provision.sh`.
- **Tests:**
  - Unit (`UnitTests/test_*`): running the script produces a CA, a server
    cert/key, and a client cert/key; `openssl verify` against the CA passes for
    both leaf certs; the client cert's subject CN equals the identity argument;
    key type / params match `CryptoBackend.transport_security()`.
  - Unit: with `openssl` absent from `PATH`, the script exits non-zero with a
    clear message (same failure posture as `dds_security_provision.sh`) and
    leaves no partial output.
- **Golden:** the `Assets/` script + its CMake wiring is copied into generated
  projects, so `test_golden.py` (+ `_java`) *may* move — regenerate with
  `HARPIA_UPDATE_GOLDEN=1` and review the diff; it should be limited to the new
  script / CMake option, nothing in message output.
- **Doc-comments:** a header block in the script itself (usage, outputs, and an
  explicit "not for production identity management — the identity store is
  task 4"), same style as `dds_security_provision.sh`.

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
