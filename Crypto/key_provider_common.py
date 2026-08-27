"""Path constants for the hand-written KeyProvider runtime headers (Track O).

Same shape as Compliance/audit_common.py's AUDIT_SINK_RUNTIME/_SRC,
Compliance/delivery_common.py's DELIVERY_RUNTIME/_SRC, and
Capability/capability_common.py's DISPATCH_RUNTIME/_SRC: the constants exist
so whichever adapter copies a header into generated output first (Track A --
DB field-level encryption of `phi` columns) does not hardcode a path into a
sibling module. No adapter copies any of these yet.

Headers and their co-copy dependencies (each *_DEPS is (name, src) tuples,
same shape as Compliance/delivery_common.py's DELIVERY_RUNTIME_DEPS):

  harpia_key_provider.h        (O.1 interface + O.3 shred + O.4 audit/zeroize)
      -> harpia_audit_sink.h   (F3; O.4 routes every key op through AuditSink)
  harpia_key_provider_local.h  (O.2 default local backend)
      -> harpia_key_provider.h  (+ its deps, transitively)
  harpia_key_provider_kms.h    (O.5 KMS/HSM reference adapter)
      -> harpia_key_provider.h  (+ its deps, transitively)

An adapter copying a backend header must copy the whole transitive set into
one directory (the #includes are all same-dir "quoted" form).
"""
import os

from Compliance.audit_common import AUDIT_SINK_RUNTIME, AUDIT_SINK_RUNTIME_SRC

_RUNTIME_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runtime")

KEY_PROVIDER_RUNTIME = "harpia_key_provider.h"
KEY_PROVIDER_RUNTIME_SRC = os.path.join(_RUNTIME_DIR, KEY_PROVIDER_RUNTIME)

#: O.4 -- harpia_key_provider.h #includes "harpia_audit_sink.h".
KEY_PROVIDER_RUNTIME_DEPS = (
    (AUDIT_SINK_RUNTIME, AUDIT_SINK_RUNTIME_SRC),
)

#: O.2 -- the default local (no-KMS) KeyProvider backend.
KEY_PROVIDER_LOCAL_RUNTIME = "harpia_key_provider_local.h"
KEY_PROVIDER_LOCAL_RUNTIME_SRC = os.path.join(
    _RUNTIME_DIR, KEY_PROVIDER_LOCAL_RUNTIME)

#: O.5 -- the KMS/HSM reference adapter backend.
KEY_PROVIDER_KMS_RUNTIME = "harpia_key_provider_kms.h"
KEY_PROVIDER_KMS_RUNTIME_SRC = os.path.join(
    _RUNTIME_DIR, KEY_PROVIDER_KMS_RUNTIME)

#: Each backend header #includes harpia_key_provider.h (whose own deps then
#: apply transitively).
KEY_PROVIDER_LOCAL_RUNTIME_DEPS = (
    (KEY_PROVIDER_RUNTIME, KEY_PROVIDER_RUNTIME_SRC),
) + KEY_PROVIDER_RUNTIME_DEPS

KEY_PROVIDER_KMS_RUNTIME_DEPS = (
    (KEY_PROVIDER_RUNTIME, KEY_PROVIDER_RUNTIME_SRC),
) + KEY_PROVIDER_RUNTIME_DEPS
