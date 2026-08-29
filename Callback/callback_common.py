"""Shared bits for the events-callbacks epic's generated event/callback
layer. Deliberately tiny, mirroring Capability/capability_common.py: the
path to the hand-written EventChannel<T> runtime every generated project
copies verbatim, and the one filter that decides which messages get an
event channel.
"""
import os

from Compliance.audit_common import (
    AUDIT_SINK_RUNTIME, AUDIT_SINK_RUNTIME_SRC)

EVENT_CACHE_RUNTIME = "harpia_event_cache.h"
EVENT_CACHE_RUNTIME_SRC = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "runtime", EVENT_CACHE_RUNTIME)

# harpia_event_cache.h #includes "harpia_audit_sink.h" (Foundation F3) at the
# same relative path (task 3 -- OnChange audit for phi), so CallbackAdapter
# ships both into generated/cpp/events/, same as ZmqAdapter does for the
# delivery runtime + its audit dependency.
EVENT_RUNTIME_COPIES = (
    (EVENT_CACHE_RUNTIME, EVENT_CACHE_RUNTIME_SRC),
    (AUDIT_SINK_RUNTIME, AUDIT_SINK_RUNTIME_SRC),
)


def is_event_message(msg):
    """True when the message carries the `event` message-type modifier (any
    of `event` / `event[cached]` / `event[not-cached]` -- all one EVENT
    token). Enums never match."""
    if getattr(msg, "isEnum", False):
        return False
    return any(tok[0] == "EVENT"
               for tok in (getattr(msg, "access_modifiers", None) or []))


def event_message_names(messages):
    """Every non-enum message that gets a generated EventChannel accessor."""
    return sorted({m.name for m in messages if is_event_message(m)})


def cache_mode_enum(msg):
    """The C++ `harpia::events::CacheMode` enumerator for this message.
    Bare `event` == Cached (the standard when unspecified)."""
    return ("NotCached" if getattr(msg, "event_cache_mode", None) == "not-cached"
            else "Cached")


def phi_field_names(msg):
    """The message's own `phi`-tagged field names (Foundation F2), in
    declaration order -- the value-free `detail` string for the channel's
    OnChange audit (task 3). Empty when the message carries no phi."""
    return [v.name for v in (getattr(msg, "variables", None) or [])
            if getattr(v, "is_phi", False)]


def audit_subject(msg):
    """The channel's audit `subject`: the message's table name if it has
    one, else the message name. Identifying metadata only (Rule 5)."""
    return getattr(msg, "tableName", "") or msg.name
