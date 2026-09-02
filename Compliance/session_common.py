"""Path / name constants for the bearer-session runtime header
(transport-authn epic, task 5 -- token-sessions).

Same shape as Compliance/rbac_common.py's RBAC_RUNTIME/_SRC/_DEPS: the constant
exists so an adapter copying the header into generated output does not hardcode
a path into a sibling module.

`harpia_session.h` is the hand-written token mechanism -- issue() (mint an
HMAC-SHA256 bearer token carrying the RBAC CN + role + expiry for an already
mTLS-authenticated caller), verify() (signature + expiry + revocation ->
Verdict), from_authorization() (what a transport gate reads off an
`Authorization: Bearer` header / `authorization` call metadata), and a
mtime-reloaded RevocationList. Configuration is deployment config read from the
environment at startup (HARPIA_SESSION_KEY / _TTL / _REVOCATIONS) -- not schema,
not compiled in, the same posture as HARPIA_RBAC_MAP.

Copied verbatim next to the generated transport headers -- generated/cpp/http/
for the shared REST+SOAP bring-up (RestAdapter), generated/cpp/grpc/ for the
gRPC service impls (GrpcServiceAdapter) -- the same "copy the runtime into the
transport dir" pattern as harpia_rbac.h.

Whether the generated gate compiles the session path in at all is a
generation-time decision (Crypto.backend.transport_hardening_required(
compliance) -- the same predicate as mTLS and RBAC); this header is the
mechanism, not that policy.

Note: harpia_session.h #includes "harpia_audit_sink.h" (Foundation F3) at the
same relative path, so an adapter that copies it must also land the audit-sink
header in the same directory -- SESSION_RUNTIME_DEPS carries it. (Both the RBAC
and session copies pull the same harpia_audit_sink.h into the same dir; the
copy is idempotent.)
"""
import os

from Compliance.audit_common import AUDIT_SINK_RUNTIME, AUDIT_SINK_RUNTIME_SRC

SESSION_RUNTIME = "harpia_session.h"
SESSION_RUNTIME_SRC = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "runtime", SESSION_RUNTIME)

#: harpia_session.h #includes "harpia_audit_sink.h" at the same relative path.
SESSION_RUNTIME_DEPS = ((AUDIT_SINK_RUNTIME, AUDIT_SINK_RUNTIME_SRC),)
