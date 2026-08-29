"""Path constant for the shared DDS frame IDL (dds-transport epic, task 2b).

Same shape as Compliance/delivery_common.py's DELIVERY_RUNTIME/_SRC and
Compliance/audit_common.py's AUDIT_SINK_RUNTIME/_SRC: the constant exists so
DdsAdapter, copying the IDL into generated output, does not hardcode a path
into a sibling module.

`harpia_dds_frame.idl` is the one opaque topic type every generated DDS
transport publishes on -- a keyed `message_type` string plus the
serialized-protobuf `payload`, the same wire bytes ZMQ/gRPC move. DdsAdapter
copies it into generated/cpp/dds/ (alongside the per-message *_dds.h
headers) whenever at least one `dds` transport-bearing message exists; the
consuming CMake runs idlc + idlcxx on it.
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
