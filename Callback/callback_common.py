"""Shared bits for the events-callbacks epic's generated event/callback
layer. Deliberately tiny, mirroring Capability/capability_common.py: the
path to the hand-written EventChannel<T> runtime every generated project
copies verbatim, and the one filter that decides which messages get an
event channel.
"""
import os

EVENT_CACHE_RUNTIME = "harpia_event_cache.h"
EVENT_CACHE_RUNTIME_SRC = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "runtime", EVENT_CACHE_RUNTIME)


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
