"""Path constants for the DDS runtime files DdsAdapter copies into generated
output (dds-transport epic): the shared frame IDL (task 2b) and the
DDS-Security scaffolding (task 3).

Same shape as Compliance/delivery_common.py's DELIVERY_RUNTIME/_SRC and
Compliance/audit_common.py's AUDIT_SINK_RUNTIME/_SRC: the constants exist so
DdsAdapter, copying these into generated output, does not hardcode a path
into a sibling module.

`harpia_dds_frame.idl` is the one opaque topic type every generated DDS
transport publishes on -- a keyed `message_type` string plus the
serialized-protobuf `payload`, the same wire bytes ZMQ/gRPC move. DdsAdapter
copies it into generated/cpp/dds/ (alongside the per-message *_dds.h
headers) whenever at least one `dds` transport-bearing message exists; the
consuming CMake runs idlc + idlcxx on it.

The DDS_SECURITY_* / DDS_GOVERNANCE_* constants point at the hand-written
`harpia_dds_security.h` helper and the static `dds_governance.xml` (task 3),
emitted into generated/cpp/dds/ + generated/cpp/dds/security/ on the same
"any `dds` message" condition; `permissions.xml` is rendered per project
(not copied) and `dds_security_selection.json` is written from the F5
CryptoBackend seam.
"""
import os

DDS_FRAME_IDL = "harpia_dds_frame.idl"
DDS_FRAME_IDL_SRC = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), os.pardir,
    "DdsAdapter", "runtime", DDS_FRAME_IDL)
DDS_FRAME_IDL_SRC = os.path.normpath(DDS_FRAME_IDL_SRC)

#: Module name / struct name the idlcxx-generated C++ lands under
#: (`harpia_dds::Frame`), and the generated header idlcxx emits for the IDL
#: stem.
DDS_FRAME_NAMESPACE = "harpia_dds"
DDS_FRAME_TYPE = "Frame"
DDS_FRAME_HEADER = "harpia_dds_frame.hpp"

_RUNTIME_DIR = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), os.pardir,
    "DdsAdapter", "runtime"))

#: dds-transport epic, task 3 -- OMG DDS-Security wiring. The hand-written
#: runtime helper (`harpia::dds_security`: `SecurityFiles`,
#: `scoped_security_config`, `secured_participant`) DdsAdapter copies next to
#: the per-message headers, and the static governance document it copies into
#: `dds/security/`. `permissions.xml` is rendered per project from
#: `DdsAdapter/templates/permissions.xml.tmpl` (topic list = the schema's
#: `dds` message names), not copied. `dds_security_selection.json` records
#: the F5 `CryptoBackend` choice + whether the compliance profile mandates
#: hardened transport.
DDS_SECURITY_RUNTIME = "harpia_dds_security.h"
DDS_SECURITY_RUNTIME_SRC = os.path.join(_RUNTIME_DIR, DDS_SECURITY_RUNTIME)
DDS_GOVERNANCE = "governance.xml"
DDS_GOVERNANCE_SRC = os.path.join(_RUNTIME_DIR, "dds_governance.xml")
DDS_PERMISSIONS = "permissions.xml"
DDS_SECURITY_SELECTION = "dds_security_selection.json"
DDS_SECURITY_DIR = "security"
