// Ships verbatim into every Java-target build (see JavaZmqAdapter.py). Hand-
// written, NOT generated -- unlike the C++ target's ZmqAdapter (a per-
// message header with 4 generated classes: <name>_sender/_receiver/
// _publisher/_subscriber), the actual transport/origin-stamping logic here
// lives ONCE in this shared class. protobuf-java's common Message
// interface plus JeroMQ's plain byte[] send/recv (vs. C++'s manual
// SerializeToString + zmq::message_t copy) make the per-message part
// trivial enough that only a thin per-message factory
// (com.harpia.generated.zmq.<name>_zmq, see templates/zmq.java.tmpl) needs
// generating -- same "reflection over per-type generated code" choice
// already made for JdbcBind/HarpiaJson/HarpiaXml, see JavaZmqAdapter/
// CLAUDE.md.
//
// CURVE (J.19): CurveKeys + the trailing-optional-parameter constructor
// overloads below are the encryption-only (no ZAP client-key allowlist --
// any client presenting valid CURVE crypto is accepted, the ZMQ analogue
// of TLS with no client certs) equivalent of the C++ runtime's
// CurveServerKeys/CurveClientKeys structs (ZmqAdapter/CLAUDE.md). Key
// encoding confirmed against JeroMQ's public org.zeromq.ZMQ.Curve API
// (see histories/ZMQ/confirm-JeroMQ-CURVE-support.md and this class's own
// generateCurveKeyPair() below) -- not yet run against a real JDK in this
// environment, same caveat as every other Java integration test in this
// thread.
package com.harpia.runtime.zmq;

import com.google.protobuf.Descriptors.FieldDescriptor;
import com.google.protobuf.InvalidProtocolBufferException;
import com.google.protobuf.Message;
import java.security.SecureRandom;
import java.util.concurrent.atomic.AtomicLong;
import org.zeromq.SocketType;
import org.zeromq.ZContext;
import org.zeromq.ZMQ;

public final class HarpiaZmq {
    private HarpiaZmq() {}

    private static final AtomicLong RUNTIME_COUNTER = new AtomicLong(0);
    private static final SecureRandom RANDOM = new SecureRandom();

    // A random-per-JVM-instance stand-in for a real OS pid, established once
    // at class-init time. `java.lang.ProcessHandle` (the obvious JDK9+
    // choice) is unavailable on Android's ART runtime (confirmed by
    // ZmqClientAndroidTest's connectedAndroidTest run -- NoClassDefFoundError
    // resolving java.lang.ProcessHandle), and this class ships to both the
    // desktop/server target and Android, so it can't reference it. A fresh
    // 64-bit random value distinguishes processes at least as well as a real
    // pid would (better, even -- OS pids get reused over a host's lifetime,
    // this never does) for this field's actual purpose below.
    private static final long PROCESS_ID = RANDOM.nextLong();

    // Runtime-unique sender id for many-to-* (push/pushpull) publishers,
    // where a shared compile-time id would make every "many" sender
    // indistinguishable (process.md 1.3.1.1). Mirrors the C++ runtime's
    // runtime_origin_id(): a process-unique id + a per-process monotonic
    // counter + random bits, so concurrent senders across processes and
    // within one process never collide -- no coordinating broker/service
    // needed. Called fresh per sender/publisher construction, not cached.
    public static String runtimeOriginId() {
        long seq = RUNTIME_COUNTER.getAndIncrement();
        long rand = RANDOM.nextLong();
        return PROCESS_ID + "-" + seq + "-" + Long.toHexString(rand);
    }

    // A generated keypair, raw 32-byte keys (index 0 = public, index 1 =
    // secret) -- ZMQ.Curve.generateKeyPair() returns Z85-encoded 40-char
    // Strings; the socket-option setters (setCurvePublicKey/
    // setCurveSecretKey/setCurveServerKey) want the raw bytes, so this
    // decodes once here rather than leaving every caller to remember to.
    public static byte[][] generateCurveKeyPair() {
        ZMQ.Curve.KeyPair kp = ZMQ.Curve.generateKeyPair();
        return new byte[][] {ZMQ.Curve.z85Decode(kp.publicKey), ZMQ.Curve.z85Decode(kp.secretKey)};
    }

    // CURVE key material for one socket. Bind side (PULL receiver / PUB
    // publisher) only needs its own secret key -- CURVE_SERVER accepts any
    // client with valid crypto; connect side (PUSH sender / SUB
    // subscriber) needs the peer's public key plus its own keypair. Which
    // one applies is decided by which factory method built this instance,
    // not re-derived from the fields at apply time.
    public static final class CurveKeys {
        private final boolean server;
        private final byte[] secretKey;
        private final byte[] publicKey;
        private final byte[] serverPublicKey;

        private CurveKeys(boolean server, byte[] secretKey, byte[] publicKey,
                          byte[] serverPublicKey) {
            this.server = server;
            this.secretKey = secretKey;
            this.publicKey = publicKey;
            this.serverPublicKey = serverPublicKey;
        }

        public static CurveKeys server(byte[] secretKey) {
            return new CurveKeys(true, secretKey, null, null);
        }

        public static CurveKeys client(byte[] serverPublicKey, byte[] publicKey, byte[] secretKey) {
            return new CurveKeys(false, secretKey, publicKey, serverPublicKey);
        }

        // Must run before bind/connect -- matches the C++ runtime's own
        // ordering (curve options set, then socket_.{connect|bind}(...)).
        void applyTo(ZMQ.Socket socket) {
            if (server) {
                socket.setCurveServer(true);
                socket.setCurveSecretKey(secretKey);
            } else {
                socket.setCurveServerKey(serverPublicKey);
                socket.setCurvePublicKey(publicKey);
                socket.setCurveSecretKey(secretKey);
            }
        }
    }

    // The message's ORIGINATOR field (name may carry a hash suffix -- see
    // message/FieldMap.py's front-end injection), or null if it declares
    // none. Found by name prefix, same rule ZmqAdapter.py's C++ generator
    // already uses (`v.name.startswith("ORIGINATOR")`).
    private static FieldDescriptor originatorField(Message prototype) {
        for (FieldDescriptor fd : prototype.getDescriptorForType().getFields()) {
            if (fd.getName().startsWith("ORIGINATOR")) {
                return fd;
            }
        }
        return null;
    }

    // PUSH sender (connect) or PUB publisher (bind), depending on `bind`.
    // Stamps `origin` into the message's ORIGINATOR field (if any) before
    // sending, same as the C++ runtime's sender.tmpl.
    public static final class Sender {
        private final ZMQ.Socket socket;
        private final String origin;
        private final FieldDescriptor originatorField;

        public Sender(ZContext ctx, SocketType type, String endpoint, boolean bind,
                      String origin, Message prototype) {
            this(ctx, type, endpoint, bind, origin, prototype, null);
        }

        // Trailing curve defaults to disabled (null), so callers who don't
        // pass one get today's plaintext behavior unchanged (J.18).
        public Sender(ZContext ctx, SocketType type, String endpoint, boolean bind,
                      String origin, Message prototype, CurveKeys curve) {
            this.socket = ctx.createSocket(type);
            if (curve != null) {
                curve.applyTo(socket);
            }
            if (bind) {
                socket.bind(endpoint);
            } else {
                socket.connect(endpoint);
            }
            this.origin = origin;
            this.originatorField = originatorField(prototype);
        }

        public String origin() {
            return origin;
        }

        public boolean send(Message msg) {
            Message toSend = msg;
            if (originatorField != null) {
                toSend = msg.toBuilder().setField(originatorField, origin).build();
            }
            return socket.send(toSend.toByteArray(), 0);
        }

        public ZMQ.Socket socket() {
            return socket;
        }
    }

    // PULL receiver (bind) or SUB subscriber (connect + subscribe-all,
    // when `subscribeAll`), depending on `bind`/`subscribeAll`.
    public static final class Receiver {
        private final ZMQ.Socket socket;

        public Receiver(ZContext ctx, SocketType type, String endpoint, boolean bind,
                        boolean subscribeAll) {
            this(ctx, type, endpoint, bind, subscribeAll, null);
        }

        // Trailing curve defaults to disabled (null), so callers who don't
        // pass one get today's plaintext behavior unchanged (J.18).
        public Receiver(ZContext ctx, SocketType type, String endpoint, boolean bind,
                        boolean subscribeAll, CurveKeys curve) {
            this.socket = ctx.createSocket(type);
            if (curve != null) {
                curve.applyTo(socket);
            }
            if (bind) {
                socket.bind(endpoint);
            } else {
                socket.connect(endpoint);
            }
            if (subscribeAll) {
                socket.subscribe(new byte[0]);
            }
        }

        // Blocking receive into `builder`. False on a closed/interrupted
        // socket or a payload that doesn't parse as this builder's type --
        // never throws for either case, same boolean-outcome convention as
        // JdbcBind/HarpiaXml.
        public boolean receive(Message.Builder builder) {
            byte[] data = socket.recv(0);
            if (data == null) {
                return false;
            }
            try {
                builder.mergeFrom(data);
                return true;
            } catch (InvalidProtocolBufferException e) {
                return false;
            }
        }

        public ZMQ.Socket socket() {
            return socket;
        }
    }
}
