"""Path / name constants for the gRPC transport-security files
GrpcServiceAdapter emits into generated output (transport-authn epic, task 2 --
mtls-grpc).

Same shape as Compliance/dds_common.py's DDS_SECURITY_* constants: the names
live here so GrpcServiceAdapter, copying the hand-written mTLS helper into
generated output, does not hardcode a path into a sibling module.

- `harpia_grpc_mtls.h` -- the hand-written credentials mechanism
  (`harpia::grpc_transport`: `MtlsFiles`, `SecurityRefused`,
  `server_credentials`, `channel_credentials`). Copied verbatim into
  generated/cpp/grpc/ whenever the schema has at least one table-bearing
  message (i.e. whenever any <name>_grpc.h is emitted).
- `grpc_server_bringup.h` -- rendered per project from
  Database/templates/grpc_server_bringup.h.tmpl: `#include`s every emitted
  <name>_grpc.h, bakes in `kHardeningRequired` from
  Crypto.backend.transport_hardening_required(compliance), and defines the
  project-wide `harpia::grpc_transport::GrpcServer` bring-up class.
- `grpc_server_selection.json` -- records the F5 CryptoBackend choice
  (openssl / openssl_fips, driven by risk_class/topology, never per
  jurisdiction) plus whether the compliance profile mandates hardened
  transport. Same field set as dds_security_selection.json.
"""
import os

_RUNTIME_DIR = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), os.pardir,
    "Database", "runtime"))

#: transport-authn epic, task 2 -- the hand-written gRPC mTLS credentials
#: helper GrpcServiceAdapter copies next to the per-message service impls.
GRPC_MTLS_RUNTIME = "harpia_grpc_mtls.h"
GRPC_MTLS_RUNTIME_SRC = os.path.join(_RUNTIME_DIR, GRPC_MTLS_RUNTIME)

#: rendered per project (not copied) -- the project-wide server bring-up.
GRPC_SERVER_BRINGUP = "grpc_server_bringup.h"

#: written per project from the F5 CryptoBackend seam.
GRPC_SERVER_SELECTION = "grpc_server_selection.json"
