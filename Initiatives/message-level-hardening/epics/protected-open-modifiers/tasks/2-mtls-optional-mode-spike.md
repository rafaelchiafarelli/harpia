## Spike: can one REST/SOAP server serve both gated and anonymous routes?

- **Depends on:** nothing (independent of task 1; can run in parallel).
- **This is a go/no-go gate, not ordinary feature work.** Its deliverable is
  a written finding, plus a minimal throwaway/reference proof, not
  production wiring — task 3 depends on the answer, not on this task's code.
- **Question to answer:** can Crow (as vendored under `third_party/`, the
  same build used by `HarpiaTest/app_example/consumer -DUSE_TLS=ON`) be
  configured so a client cert is **requested but not required** — i.e. the
  TLS handshake succeeds either way, and the handler can reliably distinguish
  "connected with no cert" from "connected with a cert that failed to
  verify"? `Database/auth_gate.py`'s `authz_*` helpers already treat an empty
  `req.client_cert_cn` as anonymous — confirm that's actually what an
  unpresented-cert connection produces under requested-not-required mode,
  as opposed to the connection being refused outright or the CN field being
  ambiguous between "no cert" and "cert present but CN empty."
- **Also answer for gRPC:** gRPC's channel-level TLS has no per-call
  optionality the way HTTP does. Confirm whether "open" for a gRPC message
  can mean "skip the RBAC role check, allow calls with no verified peer
  identity" without weakening the channel's own TLS requirement (if any) —
  this is a smaller, related question, not the same spike infrastructure.
- **Deliverable:** a short written finding (a markdown note in this task
  file or a linked doc) stating: works as needed / works with caveats (name
  them) / doesn't work, plus whichever minimal proof-of-concept code backs
  the finding. If the answer is "doesn't work cleanly," stop here and bring
  the finding back — do not have task 3 improvise a fallback (e.g. two
  listening ports) without that being a separate, explicit decision.
- **Out of scope:** any change to `Database/auth_gate.py` or the adapters
  (task 3) — this task only establishes feasibility.

## Finding: works as needed. Go.

Neither Crow/asio/OpenSSL nor gRPC's C++ API blocks "requested, not
required." Both stacks already expose the exact override surface needed
through an existing "hand the library a fully-built context/options" escape
hatch, and both current hard-coded choices live in the same two
hand-written, verbatim-copied helpers task 3 will touch — this is a small,
isolated change, not a library limitation and not a two-listening-ports
workaround.

- **REST/SOAP (Crow).** `Database/runtime/harpia_http_mtls.h`'s
  `make_server_context()` ORs `asio::ssl::verify_fail_if_no_peer_cert` onto
  `verify_peer`. Crow's `app.ssl(asio::ssl::context&&)` overload (the one
  harpia already uses, precisely because Crow's own `.ssl_file()` can't do
  real mTLS) hands the caller a fully-built `asio::ssl::context`, so nothing
  stops setting `verify_peer` alone. Dropping `verify_fail_if_no_peer_cert`
  lets a certless client complete the handshake; `crow::request::
  client_cert_cn` (the `[harpia patch]` in `third_party/crow/crow.h`) then
  comes back `""` for that connection — the exact input
  `Compliance/runtime/harpia_rbac.h`'s `decide()` already treats as
  `unauthenticated`, unchanged. A client that DOES present a cert is still
  fully verified against the loaded CA (`verify_peer` alone still verifies
  anything presented — it only stops *requiring* one); a cert from an
  untrusted CA is refused at the handshake exactly as under today's full
  mTLS.
- **gRPC.** `Database/runtime/harpia_grpc_mtls.h`'s `server_credentials()`
  hard-codes `GRPC_SSL_REQUEST_AND_REQUIRE_CLIENT_CERTIFICATE_AND_VERIFY`.
  gRPC's `grpc_ssl_client_certificate_request_type` enum has a
  request-but-don't-require sibling,
  `GRPC_SSL_REQUEST_CLIENT_CERTIFICATE_AND_VERIFY` (drop "REQUIRE"). A
  certless channel still completes the handshake; `ServerContext::
  auth_context()`'s CN lookup (already what `Database/auth_gate.py`'s
  `peer_cn()` reads) comes back empty, and the *already-generated,
  unmodified* `<name>_service::rbac_check()` resolves that to
  `Decision::unauthenticated` on its own — zero `auth_gate.py` changes
  needed for this half either. A cert from an untrusted CA is refused at the
  transport exactly as today.

**Proof-of-concept:** `UnitTests/test_mtls_optional_mode_spike.py` (see its
module docstring for the full writeup). Two live, toolchain-gated tests,
neither touching `auth_gate.py` or any adapter:
- `test_rest_optional_client_cert` — a throwaway Crow server built with its
  own hand-rolled `asio::ssl::context` (`verify_peer` only, no
  `fail_if_no_peer_cert`). Three real HTTPS connections: no cert → connects,
  `/whoami` returns `""`; trusted-CA client cert → connects, `/whoami`
  returns the cert's CN; a cert signed by a *different* CA → handshake
  fails.
- `test_grpc_optional_client_cert` — the real, unmodified generated
  `users_service` fronted by a throwaway `ServerBuilder` using
  `GRPC_SSL_REQUEST_CLIENT_CERTIFICATE_AND_VERIFY` instead of
  `harpia_grpc_mtls.h`. Same three cases via a real `push` RPC: no cert →
  `UNAUTHENTICATED` (not a transport failure); trusted cert (mapped to
  `admin` via `HARPIA_RBAC_MAP`) → `OK`; untrusted-CA cert → rejected at the
  transport.

Both pass in Docker (`Docker/run.sh pytest
UnitTests/test_mtls_optional_mode_spike.py`).

**Implication for task 3:** the fix in each helper is a one-value change
(e.g. a tri-state `hardening_mode` in place of today's `hardening_required`
bool, or a second per-message context/credentials builder) — task 3 should
decide the exact shape of that knob, not re-derive feasibility.
