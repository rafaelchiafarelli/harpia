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
// CURVE (J.19) is NOT implemented here -- this is J.18's plaintext-only
// scope. See JavaZmqAdapter/CLAUDE.md.
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

    // Runtime-unique sender id for many-to-* (push/pushpull) publishers,
    // where a shared compile-time id would make every "many" sender
    // indistinguishable (process.md 1.3.1.1). Mirrors the C++ runtime's
    // runtime_origin_id(): pid + a per-process monotonic counter + random
    // bits, so concurrent senders across processes and within one process
    // never collide -- no coordinating broker/service needed. Called fresh
    // per sender/publisher construction, not cached.
    public static String runtimeOriginId() {
        long pid = ProcessHandle.current().pid();
        long seq = RUNTIME_COUNTER.getAndIncrement();
        long rand = RANDOM.nextLong();
        return pid + "-" + seq + "-" + Long.toHexString(rand);
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
            this.socket = ctx.createSocket(type);
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
            this.socket = ctx.createSocket(type);
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
