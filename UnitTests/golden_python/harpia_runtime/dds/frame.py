"""The shared DDS topic type, ``harpia_dds::Frame`` (the Python side of
``DdsAdapter/runtime/harpia_dds_frame.idl``).

Hand-written, copied into a generated project as
``harpia_runtime.dds.frame``. It declares exactly the C++ type -- module
``harpia_dds``, ``@appendable``, a ``@key`` ``message_type`` string and a
``sequence<octet>`` payload -- so Python and C++ (``ddscxx``) readers and
writers match on the same topic (XTypes type information, checked against a
C++ peer in ``UnitTests/test_py_dds.py``). The payload is the serialized
protobuf message: the same bytes the ZMQ and gRPC transports move.
"""
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from cyclonedds.idl import IdlStruct
from cyclonedds.idl.annotations import appendable, key
from cyclonedds.idl.types import sequence, uint8

if TYPE_CHECKING:
    # cyclonedds' ``sequence`` is not generic for mypy; statically the payload
    # is any sequence of byte values (``bytes`` when writing, ``list[int]``
    # when read back)
    Octets = Sequence[int]
else:
    Octets = sequence[uint8]  # what cyclonedds reads: IDL sequence<octet>


@dataclass
@appendable
class Frame(IdlStruct, typename="harpia_dds::Frame"):
    """One harpia message on a DDS topic."""

    #: the harpia message name (the DDS instance key)
    message_type: str
    key("message_type")
    #: the serialized protobuf message (read back as a list of ints)
    payload: Octets
