"""Path / name constants for the REST+SOAP transport-security files
RestAdapter emits into generated output (transport-authn epic, task 3 --
mtls-rest-soap).

Same shape as Compliance/grpc_common.py. REST and SOAP share one
`crow::SimpleApp`, so there is one combined bring-up, emitted into
generated/cpp/http/ (a neutral dir, not rest/ or soap/):

- `harpia_http_mtls.h` -- hand-written mechanism: builds a server-side
  `asio::ssl::context` configured for mTLS (client cert required AND verified),
  handed to crow via `app.ssl(std::move(ctx))`. Fail-safe -- incomplete
  `MtlsFiles` throws `SecurityRefused`, never a silent plaintext server.
  Copied verbatim whenever RestAdapter emits any `<name>_rest.h`.
- `http_server_bringup.h` -- rendered per project from
  Database/templates/http_server_bringup.h.tmpl: `#include`s every
  `<name>_rest.h` + `<name>_soap.h`, registers every route on one
  `crow::SimpleApp`, bakes `kHardeningRequired` from
  Crypto.backend.transport_hardening_required(compliance), and (when hardened)
  configures the app for mTLS. A `static_assert` refuses to build a hardened
  project without `-DCROW_ENABLE_SSL`.
- `http_server_selection.json` -- the F5 CryptoBackend choice + hardening flag,
  same field set as dds_security_selection.json / grpc_server_selection.json.
"""
import os

_RUNTIME_DIR = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), os.pardir,
    "Database", "runtime"))

#: transport-authn epic, task 3 -- the hand-written REST/SOAP mTLS context
#: helper RestAdapter copies into generated/cpp/http/.
HTTP_MTLS_RUNTIME = "harpia_http_mtls.h"
HTTP_MTLS_RUNTIME_SRC = os.path.join(_RUNTIME_DIR, HTTP_MTLS_RUNTIME)

#: rendered per project (not copied) -- the shared REST+SOAP server bring-up.
HTTP_SERVER_BRINGUP = "http_server_bringup.h"

#: written per project from the F5 CryptoBackend seam.
HTTP_SERVER_SELECTION = "http_server_selection.json"

#: output subdir under generated/cpp/ for the combined HTTP bring-up.
HTTP_OUT_SUBDIR = "http"
