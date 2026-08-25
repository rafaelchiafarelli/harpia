"""Shared bits for the three transport-specific capability-handshake adapters
(GrpcCapabilityAdapter, HttpCapabilityAdapter, ZmqCapabilityAdapter). See
plans/message-versioning.md S5. Deliberately tiny -- each adapter still owns
its own transport-specific template/runtime; this only factors out the two
things that are genuinely identical across all three: which message types
get advertised, and the path to the shared (transport-agnostic) Dispatcher
runtime every one of them copies into its output.
"""
import os

DISPATCH_RUNTIME = "harpia_capability_dispatch.h"
DISPATCH_RUNTIME_SRC = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "runtime", DISPATCH_RUNTIME)


def message_type_names(messages):
    """Every non-enum message type name a generated peer knows about --
    the capability set advertised by all three transports. Deliberately does
    NOT filter on tableName (unlike GrpcServiceAdapter/RestAdapter/etc.):
    capability is about whether the peer's generated code knows the type
    exists at all, not whether it has DB backing."""
    return sorted({m.name for m in messages if not getattr(m, "isEnum", False)})
