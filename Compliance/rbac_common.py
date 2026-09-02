"""Path / name constants for the RBAC gate runtime header
(transport-authn epic, task 4 -- rbac).

Same shape as Compliance/audit_common.py's AUDIT_SINK_RUNTIME/_SRC and
Compliance/delivery_common.py: the constant exists so an adapter copying the
header into generated output does not hardcode a path into a sibling module.

`harpia_rbac.h` is the hand-written three-role gate mechanism -- Role
(admin/main/guest), the fixed role x operation matrix, RoleMap (identity ->
role, read once at startup from the HARPIA_RBAC_MAP file), and decide()
(returns allow / unauthenticated / forbidden, emitting exactly one AuditSink
"rbac_denied" record per non-allow). Copied verbatim next to the generated
transport headers -- generated/cpp/http/ for the shared REST+SOAP bring-up
(RestAdapter), generated/cpp/grpc/ for the gRPC service impls
(GrpcServiceAdapter) -- the same "copy the runtime into the transport dir"
pattern as harpia_grpc_mtls.h / harpia_http_mtls.h.

Whether the generated gate compiles the RBAC path in at all is a
generation-time decision (Crypto.backend.transport_hardening_required(
compliance)); this header is the mechanism, not that policy.

Note: harpia_rbac.h #includes "harpia_audit_sink.h" (Foundation F3), so an
adapter that copies the RBAC header must also copy the audit-sink header into
the same output directory -- RBAC_RUNTIME_DEPS carries it.
"""
import os

from Compliance.audit_common import AUDIT_SINK_RUNTIME, AUDIT_SINK_RUNTIME_SRC

RBAC_RUNTIME = "harpia_rbac.h"
RBAC_RUNTIME_SRC = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "runtime", RBAC_RUNTIME)

#: harpia_rbac.h #includes "harpia_audit_sink.h" at the same relative path, so
#: both must land in the same directory when copied into output.
RBAC_RUNTIME_DEPS = ((AUDIT_SINK_RUNTIME, AUDIT_SINK_RUNTIME_SRC),)
