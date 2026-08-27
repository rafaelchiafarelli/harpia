"""Path constant for the hand-written KeyProvider runtime header (Track O,
Session O.1).

Same shape as Compliance/audit_common.py's AUDIT_SINK_RUNTIME/_SRC,
Compliance/delivery_common.py's DELIVERY_RUNTIME/_SRC, and
Capability/capability_common.py's DISPATCH_RUNTIME/_SRC: the constant exists
so whichever adapter copies the header into generated output first (Track A
-- DB field-level encryption of `phi` columns) does not hardcode a path into
a sibling module. No adapter copies it yet -- O.1 is the interface + shape
only.

harpia_key_provider.h (O.1, the interface) has no harpia-internal include
dependencies -- C++ standard library only. harpia_key_provider_local.h
(O.2, the default local backend) #includes the O.1 header at the same
relative path, so an adapter copying the local backend must copy both into
one directory -- KEY_PROVIDER_LOCAL_RUNTIME_DEPS names that co-copy, same
shape as Compliance/delivery_common.py's DELIVERY_RUNTIME_DEPS.

O.4 adds AuditSink wiring to the interface; if that lands as an #include of
harpia_audit_sink.h, harpia_key_provider.h grows its own DEPS tuple then.
"""
import os

_RUNTIME_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runtime")

KEY_PROVIDER_RUNTIME = "harpia_key_provider.h"
KEY_PROVIDER_RUNTIME_SRC = os.path.join(_RUNTIME_DIR, KEY_PROVIDER_RUNTIME)

#: O.2 -- the default local (no-KMS) KeyProvider backend.
KEY_PROVIDER_LOCAL_RUNTIME = "harpia_key_provider_local.h"
KEY_PROVIDER_LOCAL_RUNTIME_SRC = os.path.join(
    _RUNTIME_DIR, KEY_PROVIDER_LOCAL_RUNTIME)

#: harpia_key_provider_local.h pulls in harpia_key_provider.h at the same
#: relative path, so both must land in the same directory when copied.
KEY_PROVIDER_LOCAL_RUNTIME_DEPS = (
    (KEY_PROVIDER_RUNTIME, KEY_PROVIDER_RUNTIME_SRC),
)
