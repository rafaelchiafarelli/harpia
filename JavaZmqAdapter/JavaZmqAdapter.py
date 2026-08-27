"""Sessions J.18/J.19 (Initiatives/multi-language-targets/thread-1-java-
target/histories/ZMQ/) -- ZMQ core transport (J.18) + CURVE-secured
variant (J.19) for the Java target.

org.zeromq:jeromq (pure-Java ZMTP reimplementation -- no JNI, no native
library, no per-platform build). Reuses ZmqAdapter.py's own
_origin_id()/_is_one_to_many() (the exact same deterministic-id
derivation and one-to-* classification the C++ target uses -- not a
re-implementation, an import) to decide each message's default origin id.

Ships the shared runtime/HarpiaZmq.java (Sender/Receiver, generic over any
Message via reflection -- see its own header comment for why this
collapses what's 4 generated classes per message in C++ into one shared
class + a thin per-message factory here) and generates
com.harpia.generated.zmq.<name>_zmq for every message that declares a
transport modifier (PUSH/PULL -> sender/receiver, EVENT/STREAM ->
publisher/subscriber), same filter as the C++ target. Each factory method
also gets a CURVE-taking overload (J.19, HarpiaZmq.CurveKeys) -- the bind
side (receiver/publisher) needs CurveKeys.server(...), the connect side
(sender/subscriber) needs CurveKeys.client(...), matching the C++
runtime's own bind-vs-connect key-role split.
"""
import os

from Logger.logger import logger
from Errors.Error import Error, Types, Classes
from Util.util import copy_if_different, write_if_different, loadTemplate
from ZmqAdapter.ZmqAdapter import _origin_id, _is_one_to_many

_RUNTIME_FILE = "HarpiaZmq.java"
_RUNTIME_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "runtime", _RUNTIME_FILE)
_RUNTIME_PACKAGE_DIR = ("com", "harpia", "runtime", "zmq")

_TEMPLATE = loadTemplate(__file__, "zmq.java.tmpl")

_SENDER_FACTORY = """\
    public static HarpiaZmq.Sender newSender(ZContext ctx, String endpoint) {{
        return new HarpiaZmq.Sender(ctx, SocketType.PUSH, endpoint, false,
            {default_id_expr}, {name}.getDefaultInstance());
    }}

    // CURVE-secured (J.19): `curve` must be HarpiaZmq.CurveKeys.client(...)
    // -- a PUSH sender connects, the connect side needs the peer's public
    // key plus its own keypair.
    public static HarpiaZmq.Sender newSender(ZContext ctx, String endpoint,
            HarpiaZmq.CurveKeys curve) {{
        return new HarpiaZmq.Sender(ctx, SocketType.PUSH, endpoint, false,
            {default_id_expr}, {name}.getDefaultInstance(), curve);
    }}

    public static HarpiaZmq.Receiver newReceiver(ZContext ctx, String endpoint) {{
        return new HarpiaZmq.Receiver(ctx, SocketType.PULL, endpoint, true, false);
    }}

    // CURVE-secured (J.19): `curve` must be HarpiaZmq.CurveKeys.server(...)
    // -- a PULL receiver binds, the bind side only needs its own secret key.
    public static HarpiaZmq.Receiver newReceiver(ZContext ctx, String endpoint,
            HarpiaZmq.CurveKeys curve) {{
        return new HarpiaZmq.Receiver(ctx, SocketType.PULL, endpoint, true, false, curve);
    }}

"""

_PUBSUB_FACTORY = """\
    public static HarpiaZmq.Sender newPublisher(ZContext ctx, String endpoint) {{
        return new HarpiaZmq.Sender(ctx, SocketType.PUB, endpoint, true,
            {default_id_expr}, {name}.getDefaultInstance());
    }}

    // CURVE-secured (J.19): `curve` must be HarpiaZmq.CurveKeys.server(...)
    // -- a PUB publisher binds, the bind side only needs its own secret key.
    public static HarpiaZmq.Sender newPublisher(ZContext ctx, String endpoint,
            HarpiaZmq.CurveKeys curve) {{
        return new HarpiaZmq.Sender(ctx, SocketType.PUB, endpoint, true,
            {default_id_expr}, {name}.getDefaultInstance(), curve);
    }}

    public static HarpiaZmq.Receiver newSubscriber(ZContext ctx, String endpoint) {{
        return new HarpiaZmq.Receiver(ctx, SocketType.SUB, endpoint, false, true);
    }}

    // CURVE-secured (J.19): `curve` must be HarpiaZmq.CurveKeys.client(...)
    // -- a SUB subscriber connects, the connect side needs the peer's
    // public key plus its own keypair.
    public static HarpiaZmq.Receiver newSubscriber(ZContext ctx, String endpoint,
            HarpiaZmq.CurveKeys curve) {{
        return new HarpiaZmq.Receiver(ctx, SocketType.SUB, endpoint, false, true, curve);
    }}

"""


class JavaZmqAdapter:
    def __init__(self, messages, dest, compliance=None) -> None:
        self.compliance = compliance
        self.messages = messages
        self.dest = dest
        self.runtimeDir = os.path.join(dest, "java", "src", "main", "java",
                                       *_RUNTIME_PACKAGE_DIR)
        self.outDir = os.path.join(dest, "java", "src", "main", "java",
                                   "com", "harpia", "generated", "zmq")
        self.log = logger(outFile=None, moduleName="JavaZmqAdapter")

    @staticmethod
    def _modifiers(msg):
        mods = getattr(msg, "access_modifiers", None) or []
        return {m[0] for m in mods}

    def Process(self):
        os.makedirs(self.runtimeDir, exist_ok=True)
        copy_if_different(_RUNTIME_SRC, os.path.join(self.runtimeDir, _RUNTIME_FILE))

        os.makedirs(self.outDir, exist_ok=True)
        written = 0
        for msg in self.messages:
            if getattr(msg, "isEnum", False):
                continue
            mods = self._modifiers(msg)
            push_pull = bool(mods & {"PUSH", "PULL"})
            pub_sub = bool(mods & {"EVENT", "STREAM"})
            if not (push_pull or pub_sub):
                continue

            default_id_expr = ("ORIGIN_ID" if _is_one_to_many(mods)
                               else "HarpiaZmq.runtimeOriginId()")
            factories = ""
            if push_pull:
                factories += _SENDER_FACTORY.format(name=msg.name, default_id_expr=default_id_expr)
            if pub_sub:
                factories += _PUBSUB_FACTORY.format(name=msg.name, default_id_expr=default_id_expr)

            source = _TEMPLATE.format(
                comment="push/pull: newSender()/newReceiver()."
                        if push_pull and not pub_sub else
                        "pub/sub (streaming/event): newPublisher()/newSubscriber()."
                        if pub_sub and not push_pull else
                        "push/pull and pub/sub: all four factories.",
                name=msg.name,
                origin_id=_origin_id(msg.md5Hash, msg.name),
                factories=factories,
            )
            fileName = "{}_zmq.java".format(msg.name)
            write_if_different(os.path.join(self.outDir, fileName), source)
            written += 1

        if written == 0:
            self.log.print("no transport-bearing messages; no Java ZMQ transports")
            return Error(errCl=Classes.MESSAGES,
                         errTp=Types.NOTHING_TO_REPORT,
                         FileName=self.outDir)

        self.log.print("generated {} Java ZMQ transport(s) into {}".format(written, self.outDir))
        return None
