"""Path constant for the shared AuditSink runtime header (Foundation F3).

Deliberately tiny, same shape as Capability/capability_common.py's
DISPATCH_RUNTIME/DISPATCH_RUNTIME_SRC: no adapter copies this yet (Track A/C
haven't started), but the constant already exists so whichever adapter picks
it up first doesn't hardcode a path into a sibling module.
"""
import os

AUDIT_SINK_RUNTIME = "harpia_audit_sink.h"
AUDIT_SINK_RUNTIME_SRC = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "runtime", AUDIT_SINK_RUNTIME)
