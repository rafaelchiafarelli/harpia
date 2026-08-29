"""events-callbacks epic -- the generated in-process event/callback layer.

For every message carrying the `event` message-type modifier, emit a
header-only accessor (events/<name>_<hash>_events.h) that hands out the one
process-wide harpia::events::EventChannel<::<name>> for that type,
constructed with the message's cache mode (Cached / NotCached, from
`event[cached]` / `event[not-cached]`; bare `event` == Cached). The
hand-written EventChannel<T> runtime (Callback/runtime/harpia_event_cache.h)
is copied verbatim into generated/cpp/events/ -- same "generate the thin
per-type accessor, copy the generic runtime" split XmlAdapter uses for
harpia_xml.h and the capability adapters use for the Dispatcher.

`read` never fires an event: the CRUDL DAO (Database/CrudlAdapter.py) calls
<name>_channel().publish() only on create / update. A table-less event
message still gets the accessor here; its application publishes directly.
"""
import os

from Logger.logger import logger
from Util.util import loadTemplate, write_if_different, copy_if_different
from Callback.callback_common import (
    EVENT_RUNTIME_COPIES, is_event_message, cache_mode_enum,
    phi_field_names, audit_subject)

EVENTS_EXT = "_events.h"

_TEMPLATE = loadTemplate(__file__, "events.h.tmpl")

_MODE_DOC = {"Cached": "cached (retains the most recent value; a late "
                       "subscriber gets it immediately)",
             "NotCached": "not-cached (retains nothing; a late subscriber "
                          "gets nothing until the next publish)"}


class CallbackAdapter:
    def __init__(self, messages, dest, compliance=None) -> None:
        self.compliance = compliance
        self.messages = messages
        self.dest = dest
        self.outDir = os.path.join(dest, "generated", "cpp", "events")
        self.log = logger(outFile=None, moduleName="CallbackAdapter")

    def _render(self, msg):
        cache_mode = cache_mode_enum(msg)
        modifier = ("event[not-cached]" if cache_mode == "NotCached"
                    else "event[cached]")
        phi = phi_field_names(msg)
        return _TEMPLATE.format(
            guard="HARPIA_EVENTS_{}_{}".format(msg.name.upper(), msg.md5Hash),
            pb_header="protofiles/{}_{}.pb.h".format(msg.name, msg.md5Hash),
            cls=msg.name,
            name=msg.name,
            cache_mode=cache_mode,
            modifier=modifier,
            mode_doc=_MODE_DOC[cache_mode],
            # task 3: value-free OnChange audit metadata -- both empty for a
            # non-phi type, which makes the channel never audit.
            audit_subject=(audit_subject(msg) if phi else ""),
            audit_phi_fields=(",".join(phi)))

    def Process(self):
        event_msgs = [m for m in self.messages if is_event_message(m)]
        if not event_msgs:
            self.log.print("no event messages; no event/callback layer")
            return None

        os.makedirs(self.outDir, exist_ok=True)
        written = 0
        for msg in event_msgs:
            fileName = "{}_{}{}".format(msg.name, msg.md5Hash, EVENTS_EXT)
            write_if_different(os.path.join(self.outDir, fileName),
                               self._render(msg))
            written += 1

        # The generic EventChannel<T> runtime + its harpia_audit_sink.h
        # dependency (task 3), copied verbatim (same split as harpia_xml.h /
        # the capability Dispatcher, and the same runtime+audit pair
        # ZmqAdapter ships into delivery/). Stale per-message wrappers from a
        # renamed/removed message are reaped by main.py's one global
        # prune_stale_outputs pass over generated/.
        for name, src in EVENT_RUNTIME_COPIES:
            copy_if_different(src, os.path.join(self.outDir, name))

        self.log.print("generated {} event channel(s) into {}".format(
            written, self.outDir))
        return None
