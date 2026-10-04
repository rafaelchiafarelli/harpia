package com.harpia.multisystem.handheld;

import com.google.protobuf.Descriptors.FieldDescriptor;
import com.google.protobuf.Message;
import com.harpia.generated.field_note;
import com.harpia.generated.field_note_ID;
import com.harpia.generated.field_note_Message;
import com.harpia.generated.field_note_ServiceGrpc;
import com.harpia.generated.live_sample;
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
import io.grpc.Status;
import io.grpc.StatusRuntimeException;

import org.zeromq.ZContext;
import org.zeromq.ZMQ;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.Random;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.Consumer;

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
 * <p>Load mode (load-harness task 1, {@link Config#load}): instead of the
 * note-per-N-samples and periodic listing, one thread paces operations at
 * {@link Config#rate} picked by the {@link Config#mix} weights -- create a
 * field note / list readings / read back one of its own notes (the generated
 * gRPC surface is push, streamSrc, pullByID; there is no update RPC) -- and
 * hands one JSON line per operation to {@link Config#report}:
 * {@code {"t","client_kind":"handheld","identity","op","ok","grpc_code","latency_us"}}.
 * The subscription keeps running and reports every received sample as
 * {@code {"t","client_kind":"handheld","identity","op":"sub_recv","seq_gap"}},
 * where seq_gap counts the samples missed since the previous one from the same
 * device -- so dropped samples are visible.
 *
 * <p>All I/O comes in through {@link Config}: certificate/key bytes, not paths,
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
        /** This client's identity (its certificate CN); also the notes' author. */
        public String author = "handheld";
        public int notesEvery = 5;
        public long listEveryMs = 2000;
        /** First field_note primary key; this client uses idBase, idBase+1, ... */
        public int idBase = 1;

        // ---- load mode -----------------------------------------------------
        public boolean load;
        /** operations per second */
        public double rate = 20;
        /** create : list : read weights */
        public int[] mix = {8, 1, 1};
        /** receives one JSON line per operation / received sample; must be thread-safe */
        public Consumer<String> report = line -> { };
    }

    /** Live counters, readable from any thread. */
    public static final class Counters {
        public final AtomicLong samplesReceived = new AtomicLong();
        public final AtomicLong notesWritten = new AtomicLong();
        public final AtomicLong readingsListed = new AtomicLong();
        public final AtomicLong listCalls = new AtomicLong();
        public final AtomicLong loadOps = new AtomicLong();
        public final AtomicLong errors = new AtomicLong();
        public final AtomicReference<String> lastError = new AtomicReference<>("");

        @Override
        public String toString() {
            return "samples=" + samplesReceived.get() + " notes=" + notesWritten.get()
                + " readings_listed=" + readingsListed.get()
                + " list_calls=" + listCalls.get() + " load_ops=" + loadOps.get()
                + " errors=" + errors.get();
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
    private Thread loader;
    private ScheduledExecutorService lister;
    private int nextNoteId;

    public Handheld(Config cfg) {
        this.cfg = cfg;
        this.nextNoteId = cfg.idBase;
    }

    public Counters counters() { return counters; }

    /** Opens the channel, obtains a session, starts subscribing and listing (or the load loop). */
    public synchronized void start() {
        if (running) return;
        ManagedChannelBuilder<?> b = Grpc.newChannelBuilderForAddress(
            cfg.stationHost, cfg.stationPort,
            HarpiaGrpcTls.credentials(new java.io.ByteArrayInputStream(cfg.caPem),
                                      new java.io.ByteArrayInputStream(cfg.certPem),
                                      new java.io.ByteArrayInputStream(cfg.keyPem)));
        if (cfg.authority != null && !cfg.authority.isEmpty()) b.overrideAuthority(cfg.authority);
        channel = b.build();
        long s = System.nanoTime();
        try {
            session = HarpiaSession.issue(channel, reading_ServiceGrpc.getHeartBeatMethod());
            if (cfg.load) op("session", null, s);
        } catch (RuntimeException e) {
            if (cfg.load) op("session", e, s);
            channel.shutdownNow();
            throw e;
        }
        readings = reading_ServiceGrpc.newBlockingStub(channel).withInterceptors(session.interceptor());
        notes = field_note_ServiceGrpc.newBlockingStub(channel).withInterceptors(session.interceptor());

        running = true;
        zmq = new ZContext();
        if (cfg.subEndpoint != null) {
            subscriber = new Thread(this::subscribeLoop, "handheld-sub");
            subscriber.setDaemon(true);
            subscriber.start();
        }
        if (cfg.load) {
            loader = new Thread(this::loadLoop, "handheld-load");
            loader.setDaemon(true);
            loader.start();
        } else {
            lister = Executors.newSingleThreadScheduledExecutor(r -> {
                Thread t = new Thread(r, "handheld-list");
                t.setDaemon(true);
                return t;
            });
            lister.scheduleWithFixedDelay(this::listReadings, 0, cfg.listEveryMs, TimeUnit.MILLISECONDS);
        }
    }

    /** Stops listing / the load loop and subscribing, and closes the channel. Idempotent. */
    public synchronized void stop() {
        if (!running) return;
        running = false;
        if (lister != null) lister.shutdownNow();
        join(loader);
        join(subscriber);
        zmq.close();
        channel.shutdownNow();
        try {
            channel.awaitTermination(5, TimeUnit.SECONDS);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    private static void join(Thread t) {
        if (t == null) return;
        try {
            t.join(5000);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    private void fail(String what, Exception e) {
        counters.errors.incrementAndGet();
        counters.lastError.set(what + ": " + e.getMessage());
    }

    // ---- JSON lines (identities are [A-Za-z0-9._-]: no escaping needed) ----

    private static String now() {
        long ms = System.currentTimeMillis();
        return (ms / 1000) + "." + String.format("%03d", ms % 1000);
    }

    private void op(String name, Exception error, long startNanos) {
        long us = (System.nanoTime() - startNanos) / 1000;
        String code = "OK";
        if (error instanceof StatusRuntimeException) {
            code = ((StatusRuntimeException) error).getStatus().getCode().name();
        } else if (error != null) {
            code = Status.fromThrowable(error).getCode().name();
            if ("UNKNOWN".equals(code) && error.getMessage() != null
                    && error.getMessage().contains("refused")) code = "INTERNAL";
        }
        cfg.report.accept("{\"t\":" + now() + ",\"client_kind\":\"handheld\",\"identity\":\""
            + cfg.author + "\",\"op\":\"" + name + "\",\"ok\":" + (error == null)
            + ",\"grpc_code\":\"" + code + "\",\"latency_us\":" + us + "}");
    }

    // ---- the stream ---------------------------------------------------------

    private void subscribeLoop() {
        HarpiaZmq.CurveKeys keys = HarpiaZmq.CurveKeys.client(
            ZMQ.Curve.z85Decode(cfg.zmqServerPublic),
            ZMQ.Curve.z85Decode(cfg.zmqPublic),
            ZMQ.Curve.z85Decode(cfg.zmqSecret));
        HarpiaZmq.Receiver sub = live_sample_zmq.newSubscriber(zmq, cfg.subEndpoint, keys);
        sub.socket().setLinger(0);
        sub.socket().setReceiveTimeOut(500);
        Map<String, Long> lastSeq = new HashMap<>();
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
            if (cfg.load) {
                Long prev = lastSeq.put(s.getDeviceId(), s.getSeq());
                long gap = prev == null ? 0 : Math.max(0, s.getSeq() - prev - 1);
                cfg.report.accept("{\"t\":" + now() + ",\"client_kind\":\"handheld\",\"identity\":\""
                    + cfg.author + "\",\"op\":\"sub_recv\",\"seq_gap\":" + gap + "}");
                continue;
            }
            if (++since >= cfg.notesEvery) {
                since = 0;
                writeNote(s.build());
            }
        }
    }

    // ---- interactive mode ---------------------------------------------------

    private void writeNote(live_sample s) {
        try {
            createNote("saw " + s.getDeviceId() + " seq " + s.getSeq() + " value " + s.getValue());
            counters.notesWritten.incrementAndGet();
        } catch (RuntimeException e) {
            fail("create field_note", e);
        }
    }

    private int createNote(String text) {
        int id = nextNoteId++;               // spent even if the create fails
        field_note.Builder n = field_note.newBuilder()
            .setAuthor(cfg.author)
            .setText(text)
            .setWrittenAtMs(System.currentTimeMillis());
        setId(n, id);
        check(session.withRetry(() -> notes.withDeadlineAfter(10, TimeUnit.SECONDS)
            .push(field_note_Message.newBuilder().setMsg(n).build())), "create field_note");
        return id;
    }

    private long listReadingsOnce() {
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
        return n;
    }

    private void listReadings() {
        if (!running) return;
        try {
            listReadingsOnce();
        } catch (RuntimeException e) {
            if (running) fail("list readings", e);
        }
    }

    // ---- load mode ----------------------------------------------------------

    private void loadLoop() {
        Random rng = new Random(cfg.author.hashCode());   // deterministic per identity
        int total = cfg.mix[0] + cfg.mix[1] + cfg.mix[2];
        List<Integer> mine = new ArrayList<>();
        long periodNanos = (long) (1e9 / cfg.rate);
        long t0 = System.nanoTime();
        for (long i = 0; running; i++) {
            long due = t0 + i * periodNanos;
            long wait = due - System.nanoTime();
            if (wait > 0) {
                try {
                    TimeUnit.NANOSECONDS.sleep(wait);
                } catch (InterruptedException e) {
                    return;
                }
            }
            if (!running) return;
            int r = rng.nextInt(total);
            int kind = r < cfg.mix[0] ? 0 : r < cfg.mix[0] + cfg.mix[1] ? 1 : 2;
            if (kind == 2 && mine.isEmpty()) kind = 0;     // nothing of ours to read yet
            long s = System.nanoTime();
            String name = kind == 0 ? "create" : kind == 1 ? "list" : "read";
            try {
                if (kind == 0) {
                    mine.add(createNote("load " + i));
                    counters.notesWritten.incrementAndGet();
                } else if (kind == 1) {
                    listReadingsOnce();
                } else {
                    int id = mine.get(rng.nextInt(mine.size()));
                    session.withRetry(() -> notes.withDeadlineAfter(10, TimeUnit.SECONDS)
                        .pullByID(field_note_ID.newBuilder().setId(id).build()));
                }
                op(name, null, s);
            } catch (RuntimeException e) {
                op(name, e, s);
                fail(name, e);
            }
            counters.loadOps.incrementAndGet();
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
