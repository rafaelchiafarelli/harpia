package com.harpia.multisystem.handheld;

import com.google.protobuf.Descriptors.FieldDescriptor;
import com.google.protobuf.Message;
import com.harpia.generated.field_note;
import com.harpia.generated.field_note_Message;
import com.harpia.generated.field_note_ServiceGrpc;
import com.harpia.generated.live_sample;
import com.harpia.generated.reading;
import com.harpia.generated.reading_Message;
import com.harpia.generated.reading_ServiceGrpc;
import com.harpia.generated.reading_Stream;
import com.harpia.generated.zmq.live_sample_zmq;
import com.harpia.runtime.grpc.HarpiaGrpcTls;
import com.harpia.runtime.grpc.HarpiaSession;
import com.harpia.runtime.zmq.HarpiaZmq;

import io.grpc.Grpc;
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;

import org.zeromq.ZContext;
import org.zeromq.ZMQ;

import java.util.Iterator;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicReference;

/**
 * The reference system's handheld logic (multi-system-reference /
 * reference-system task 5) -- plain Java, no Android API, so the same code runs
 * in the Android app and in the JVM CLI (and, in the load harness, hundreds of
 * times in headless JVMs).
 *
 * <ul>
 *   <li>Subscribes to edge's {@code live_sample} stream (JeroMQ SUB, CURVE;
 *       edge's ZAP handler admits this client's public key).</li>
 *   <li>Every {@code notesEvery} samples, creates one {@code field_note} on
 *       station (gRPC over mTLS + a bearer session).</li>
 *   <li>Every {@code listEveryMs}, lists {@code reading}s from station.</li>
 * </ul>
 *
 * All I/O comes in through {@link Config}: certificate/key bytes, not paths,
 * because Android loads them from resources, not files.
 */
public final class Handheld {

    /** Everything Handheld needs from its host (CLI flags or Android resources). */
    public static final class Config {
        public String stationHost = "127.0.0.1";
        public int stationPort = 50051;
        /** TLS name to verify station's certificate against (null: stationHost). */
        public String authority;
        public byte[] caPem, certPem, keyPem;
        /** e.g. tcp://edge.lan:5556 */
        public String subEndpoint;
        /** z85 CURVE keys: edge's server public key, this client's keypair. */
        public String zmqServerPublic, zmqPublic, zmqSecret;
        public String author = "handheld";
        public int notesEvery = 5;
        public long listEveryMs = 2000;
        /** First field_note primary key; this client uses idBase, idBase+1, ... */
        public int idBase = 1;
    }

    /** Live counters, readable from any thread. */
    public static final class Counters {
        public final AtomicLong samplesReceived = new AtomicLong();
        public final AtomicLong notesWritten = new AtomicLong();
        public final AtomicLong readingsListed = new AtomicLong();
        public final AtomicLong listCalls = new AtomicLong();
        public final AtomicLong errors = new AtomicLong();
        public final AtomicReference<String> lastError = new AtomicReference<>("");

        @Override
        public String toString() {
            return "samples=" + samplesReceived.get() + " notes=" + notesWritten.get()
                + " readings_listed=" + readingsListed.get()
                + " list_calls=" + listCalls.get() + " errors=" + errors.get();
        }
    }

    private final Config cfg;
    private final Counters counters = new Counters();
    private volatile boolean running;
    private ManagedChannel channel;
    private HarpiaSession session;
    private reading_ServiceGrpc.reading_ServiceBlockingStub readings;
    private field_note_ServiceGrpc.field_note_ServiceBlockingStub notes;
    private ZContext zmq;
    private Thread subscriber;
    private ScheduledExecutorService lister;
    private int nextNoteId;

    public Handheld(Config cfg) {
        this.cfg = cfg;
        this.nextNoteId = cfg.idBase;
    }

    public Counters counters() { return counters; }

    /** Opens the channel, obtains a session, starts subscribing and listing. */
    public synchronized void start() {
        if (running) return;
        ManagedChannelBuilder<?> b = Grpc.newChannelBuilderForAddress(
            cfg.stationHost, cfg.stationPort,
            HarpiaGrpcTls.credentials(new java.io.ByteArrayInputStream(cfg.caPem),
                                      new java.io.ByteArrayInputStream(cfg.certPem),
                                      new java.io.ByteArrayInputStream(cfg.keyPem)));
        if (cfg.authority != null && !cfg.authority.isEmpty()) b.overrideAuthority(cfg.authority);
        channel = b.build();
        session = HarpiaSession.issue(channel, reading_ServiceGrpc.getHeartBeatMethod());
        readings = reading_ServiceGrpc.newBlockingStub(channel).withInterceptors(session.interceptor());
        notes = field_note_ServiceGrpc.newBlockingStub(channel).withInterceptors(session.interceptor());

        running = true;
        zmq = new ZContext();
        subscriber = new Thread(this::subscribeLoop, "handheld-sub");
        subscriber.setDaemon(true);
        subscriber.start();
        lister = Executors.newSingleThreadScheduledExecutor(r -> {
            Thread t = new Thread(r, "handheld-list");
            t.setDaemon(true);
            return t;
        });
        lister.scheduleWithFixedDelay(this::listReadings, 0, cfg.listEveryMs, TimeUnit.MILLISECONDS);
    }

    /** Stops listing and subscribing and closes the channel. Idempotent. */
    public synchronized void stop() {
        if (!running) return;
        running = false;
        lister.shutdownNow();
        try {
            subscriber.join(3000);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
        zmq.close();
        channel.shutdownNow();
        try {
            channel.awaitTermination(5, TimeUnit.SECONDS);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    private void fail(String what, Exception e) {
        counters.errors.incrementAndGet();
        counters.lastError.set(what + ": " + e.getMessage());
    }

    private void subscribeLoop() {
        HarpiaZmq.CurveKeys keys = HarpiaZmq.CurveKeys.client(
            ZMQ.Curve.z85Decode(cfg.zmqServerPublic),
            ZMQ.Curve.z85Decode(cfg.zmqPublic),
            ZMQ.Curve.z85Decode(cfg.zmqSecret));
        HarpiaZmq.Receiver sub = live_sample_zmq.newSubscriber(zmq, cfg.subEndpoint, keys);
        sub.socket().setLinger(0);
        sub.socket().setReceiveTimeOut(500);
        long since = 0;
        while (running) {
            live_sample.Builder s = live_sample.newBuilder();
            try {
                if (!sub.receive(s)) continue;            // timeout: check `running`
            } catch (RuntimeException e) {
                if (running) fail("receive", e);
                continue;
            }
            counters.samplesReceived.incrementAndGet();
            if (++since >= cfg.notesEvery) {
                since = 0;
                writeNote(s.build());
            }
        }
    }

    private void writeNote(live_sample s) {
        int id = nextNoteId++;
        field_note.Builder n = field_note.newBuilder()
            .setAuthor(cfg.author)
            .setText("saw " + s.getDeviceId() + " seq " + s.getSeq() + " value " + s.getValue())
            .setWrittenAtMs(System.currentTimeMillis());
        setId(n, id);
        try {
            check(session.withRetry(() -> notes.withDeadlineAfter(10, TimeUnit.SECONDS)
                .push(field_note_Message.newBuilder().setMsg(n).build())), "create field_note");
            counters.notesWritten.incrementAndGet();
        } catch (RuntimeException e) {
            fail("create field_note", e);
        }
    }

    private void listReadings() {
        if (!running) return;
        try {
            Iterator<reading_Message> it = session.withRetry(() -> readings
                .withDeadlineAfter(10, TimeUnit.SECONDS)
                .streamSrc(reading_Stream.newBuilder().setLimit(50).build()));
            long n = 0;
            while (it.hasNext()) {
                it.next();
                n++;
            }
            counters.readingsListed.addAndGet(n);
            counters.listCalls.incrementAndGet();
        } catch (RuntimeException e) {
            if (running) fail("list readings", e);
        }
    }

    private static void check(com.harpia.generated.errorCode ec, String what) {
        if (ec.getCode() != 0) throw new IllegalStateException(what + " refused: " + ec.getMessage());
    }

    // ID_<hash>: the hidden primary-key field, hash-suffixed per project.
    private static void setId(Message.Builder b, int id) {
        for (FieldDescriptor fd : b.getDescriptorForType().getFields()) {
            if (fd.getName().startsWith("ID_")) {
                b.setField(fd, id);
                return;
            }
        }
        throw new IllegalStateException(b.getDescriptorForType().getName() + " has no ID_ field");
    }
}
