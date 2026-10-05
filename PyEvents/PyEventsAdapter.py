"""python-target / py-events -- in-process event channels (the Python side of
``Callback/CallbackAdapter.py``).

Copies ``runtime/events.py`` as ``harpia_runtime.events`` (with the audit
sink it records into) and generates
``harpia_generated/events/<name>_<hash>_events.py`` per ``event`` message:
a module-level channel and its ``<name>_channel()`` accessor. Same filter,
cache mode and audit metadata as C++ (``Callback.callback_common``). No
``events/`` package and no runtime copy when there are no event messages.
"""
import os

from Callback.callback_common import (audit_subject, cache_mode_enum,
                                      is_event_message, phi_field_names)
from Compliance.audit_common import PY_AUDIT_SINK_MODULE, PY_AUDIT_SINK_RUNTIME_SRC
from Logger.logger import logger
from PyAdapter.runtime_copy import copy_runtime_module
from Util.util import loadTemplate, write_if_different

_TEMPLATE = loadTemplate(__file__, "events.py.tmpl")
_RUNTIME = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runtime", "events.py")
EVENTS_MODULE = "harpia_runtime.events"
EVENTS_EXT = "_events.py"
_MODE = {"Cached": "CACHED", "NotCached": "NOT_CACHED"}


class PyEventsAdapter:
    def __init__(self, messages, dest, compliance=None) -> None:
        self.compliance = compliance
        self.messages = messages
        self.dest = dest
        self.outDir = os.path.join(dest, "python", "harpia_generated", "events")
        self.log = logger(outFile=None, moduleName="PyEventsAdapter")

    def _events(self):
        return [m for m in self.messages
                if not getattr(m, "isEnum", False) and is_event_message(m)]

    def Process(self):
        events = self._events()
        if not events:
            return None
        copy_runtime_module(self.dest, _RUNTIME, EVENTS_MODULE)
        copy_runtime_module(self.dest, PY_AUDIT_SINK_RUNTIME_SRC, PY_AUDIT_SINK_MODULE)
        os.makedirs(self.outDir, exist_ok=True)
        write_if_different(os.path.join(self.outDir, "__init__.py"),
                           '"""Generated in-process event channels, one module per '
                           '``event`` message."""\n')
        for msg in events:
            write_if_different(os.path.join(
                self.outDir, "{}_{}{}".format(msg.name, msg.md5Hash, EVENTS_EXT)),
                self._render(msg))
        self.log.print("generated {} event channel(s) into {}".format(
            len(events), self.outDir))
        return None

    def _render(self, msg):
        mode = cache_mode_enum(msg)
        phi = phi_field_names(msg)
        modifier = "event[not-cached]" if mode == "NotCached" else "event"
        audit_doc = (
            "Each publish records a value-free ``phi_event_dispatch`` audit for its\n"
            "``phi`` fields ({}).".format(", ".join(phi)) if phi else
            "This type carries no ``phi``: the channel never audits a publish.")
        return _TEMPLATE.format(
            name=msg.name, hash=msg.md5Hash, modifier=modifier,
            mode_doc="cached" if mode == "Cached" else "not-cached",
            audit_doc=audit_doc, cache_mode=_MODE[mode],
            # value-free audit metadata, both empty for a non-phi type
            audit_subject=repr(audit_subject(msg) if phi else ""),
            audit_phi_fields=repr(",".join(phi)))
