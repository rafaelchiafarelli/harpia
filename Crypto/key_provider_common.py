"""Path constant for the hand-written KeyProvider runtime header (Track O,
Session O.1).

Same shape as Compliance/audit_common.py's AUDIT_SINK_RUNTIME/_SRC,
Compliance/delivery_common.py's DELIVERY_RUNTIME/_SRC, and
Capability/capability_common.py's DISPATCH_RUNTIME/_SRC: the constant exists
so whichever adapter copies the header into generated output first (Track A
-- DB field-level encryption of `phi` columns) does not hardcode a path into
a sibling module. No adapter copies it yet -- O.1 is the interface + shape
only.

harpia_key_provider.h has no harpia-internal include dependencies (C++
standard library only), so unlike delivery_common.py there is no co-copy
DEPS tuple here yet. O.4 adds AuditSink wiring to the interface; if that
lands as an #include of harpia_audit_sink.h, a DEPS tuple gets added then.
"""
import os

KEY_PROVIDER_RUNTIME = "harpia_key_provider.h"
KEY_PROVIDER_RUNTIME_SRC = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "runtime", KEY_PROVIDER_RUNTIME)
