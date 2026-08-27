"""Path constant for the shared delivery-guarantee runtime header
(sensitive-data roadmap Phase 3a).

Same shape as Compliance/audit_common.py's AUDIT_SINK_RUNTIME/_SRC and
Capability/capability_common.py's DISPATCH_RUNTIME/_SRC: the constant exists
so whichever adapter copies the header into generated output first
(ZmqAdapter, Phase 3b) does not hardcode a path into a sibling module. The
runtime (harpia_delivery.h) is transport-agnostic -- a later gRPC/DDS wiring
would copy the same file.

Note: harpia_delivery.h #includes "harpia_audit_sink.h" (its sibling in the
same runtime/ dir), so an adapter that copies the delivery header must also
copy the audit-sink header into the same output directory.
"""
import os

from Compliance.audit_common import AUDIT_SINK_RUNTIME, AUDIT_SINK_RUNTIME_SRC

DELIVERY_RUNTIME = "harpia_delivery.h"
DELIVERY_RUNTIME_SRC = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "runtime", DELIVERY_RUNTIME)

#: The delivery header pulls in the audit-sink header at the same relative
#: path, so both must land in the same directory when copied into output.
DELIVERY_RUNTIME_DEPS = ((AUDIT_SINK_RUNTIME, AUDIT_SINK_RUNTIME_SRC),)
