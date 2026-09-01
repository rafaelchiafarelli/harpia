"""Path / name constants for the ZMQ CURVE ZAP allowlist runtime header
(transport-authn epic, "zmq-zap-allowlist").

Same shape as Compliance/rbac_common.py / grpc_common.py: the names live here
so ZmqAdapter, copying the hand-written ZAP handler into generated output,
does not hardcode a path into a sibling module.

`harpia_zap.h` is the hand-written mechanism -- `harpia::zap::AllowList`
(`from_env()` reads the `HARPIA_ZMQ_ALLOWLIST` file), `ZapHandler` (a REP loop
on `inproc://zeromq.zap.01` that answers each CURVE handshake 200/400 off the
allowlist, emitting one `AuditSink` `"zap_denied"` record per denial), and
`ensure_running(::zmq::context_t&)` (idempotent per context). It lives under
`ZmqAdapter/runtime/` (transport-specific, needs cppzmq -- unlike the pure-std
`harpia_rbac.h`), the same way `harpia_grpc_mtls.h` lives under
`Database/runtime/`. Copied verbatim into `generated/cpp/zap/` whenever
ZmqAdapter emits a CURVE-server-bearing header under a hardened compliance
profile (`Crypto.backend.transport_hardening_required`).

Note: `harpia_zap.h` `#include`s `"harpia_audit_sink.h"` (Foundation F3) at the
same relative path, so an adapter copying the ZAP header must also copy the
audit-sink header into the same output directory -- `ZAP_RUNTIME_DEPS` carries
it.
"""
import os

from Compliance.audit_common import AUDIT_SINK_RUNTIME, AUDIT_SINK_RUNTIME_SRC

_RUNTIME_DIR = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), os.pardir,
    "ZmqAdapter", "runtime"))

ZAP_RUNTIME = "harpia_zap.h"
ZAP_RUNTIME_SRC = os.path.join(_RUNTIME_DIR, ZAP_RUNTIME)

#: output subdir under generated/cpp/ for the copied ZAP runtime.
ZAP_OUT_SUBDIR = "zap"

#: harpia_zap.h #includes "harpia_audit_sink.h" at the same relative path, so
#: both must land in the same directory when copied into output.
ZAP_RUNTIME_DEPS = ((AUDIT_SINK_RUNTIME, AUDIT_SINK_RUNTIME_SRC),)
