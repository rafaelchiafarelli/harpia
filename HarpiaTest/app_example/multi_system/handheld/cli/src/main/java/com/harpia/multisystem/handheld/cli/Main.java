package com.harpia.multisystem.handheld.cli;

import com.harpia.multisystem.handheld.Handheld;

import java.io.BufferedWriter;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardOpenOption;

/**
 * JVM launcher for {@link Handheld} -- the same core the Android app runs.
 * Flags mirror edge's:
 *
 * <pre>
 *   handheld --station host:port --certs DIR --identity NAME --sub tcp://edge:5556
 *            --zmq-keys DIR [--authority NAME] [--notes-every N]
 *            [--list-every MS] [--id-base N] [--duration S]
 *   handheld --load --identity NAME --rate OPS --duration S [--mix C:L:R]
 *            --report FILE.jsonl --station ... --certs DIR [--sub ... --zmq-keys DIR]
 * </pre>
 *
 * <p>Load mode (load-harness task 1): one identity, operations paced at
 * --rate and picked by the --mix weights (create note : list readings : read
 * own note), one JSON line per operation and per received sample in --report.
 * --sub is optional in load mode.
 *
 * Reads DIR/ca.pem, DIR/client_NAME.pem, DIR/client_NAME_key.pem and, from the
 * ZMQ key dir, zmq_server_public.key + zmq_NAME_public.key / _secret.key.
 * Prints the counters every 2 s and a final "handheld: done ..." line.
 */
public final class Main {

    private static String value(String[] args, int i) {
        if (i + 1 >= args.length) throw new IllegalArgumentException(args[i] + " needs a value");
        return args[i + 1];
    }

    private static String key(Path p) throws IOException {
        return new String(Files.readAllBytes(p), StandardCharsets.US_ASCII).trim();
    }

    private static int[] parseMix(String v) {
        String[] p = v.split(":");
        if (p.length != 3) throw new IllegalArgumentException("--mix wants create:list:read weights, e.g. 8:1:1");
        int[] m = {Integer.parseInt(p[0]), Integer.parseInt(p[1]), Integer.parseInt(p[2])};
        if (m[0] < 0 || m[1] < 0 || m[2] < 0 || m[0] + m[1] + m[2] == 0)
            throw new IllegalArgumentException("--mix weights must be >= 0 and not all 0");
        return m;
    }

    public static void main(String[] args) throws Exception {
        String station = "127.0.0.1:50051", certs = ".", identity = "handheld", zmqKeys = ".";
        Handheld.Config c = new Handheld.Config();
        int duration = 0;
        String report = null;
        try {
            for (int i = 0; i < args.length; i += 2) {
                if (args[i].equals("--load")) {
                    c.load = true;
                    i--;                          // a flag, no value
                    continue;
                }
                String v = value(args, i);
                switch (args[i]) {
                    case "--station": station = v; break;
                    case "--certs": certs = v; break;
                    case "--identity": identity = v; break;
                    case "--sub": c.subEndpoint = v; break;
                    case "--zmq-keys": zmqKeys = v; break;
                    case "--authority": c.authority = v; break;
                    case "--notes-every": c.notesEvery = Integer.parseInt(v); break;
                    case "--list-every": c.listEveryMs = Long.parseLong(v); break;
                    case "--id-base": c.idBase = Integer.parseInt(v); break;
                    case "--duration": duration = Integer.parseInt(v); break;
                    case "--rate": c.rate = Double.parseDouble(v); break;
                    case "--mix": c.mix = parseMix(v); break;
                    case "--report": report = v; break;
                    default: throw new IllegalArgumentException("unknown argument " + args[i]);
                }
            }
            if (c.load) {
                if (report == null || duration <= 0 || c.rate <= 0)
                    throw new IllegalArgumentException("load mode needs --report, --duration and --rate > 0");
            } else if (c.subEndpoint == null) {
                throw new IllegalArgumentException("--sub is required");
            }
        } catch (IllegalArgumentException e) {
            System.err.println("handheld: " + e.getMessage());
            System.exit(2);
        }
        int colon = station.lastIndexOf(':');
        c.stationHost = station.substring(0, colon);
        c.stationPort = Integer.parseInt(station.substring(colon + 1));
        c.author = identity;
        Path cd = Paths.get(certs), zd = Paths.get(zmqKeys);
        c.caPem = Files.readAllBytes(cd.resolve("ca.pem"));
        c.certPem = Files.readAllBytes(cd.resolve("client_" + identity + ".pem"));
        c.keyPem = Files.readAllBytes(cd.resolve("client_" + identity + "_key.pem"));
        if (c.subEndpoint != null) {
            c.zmqServerPublic = key(zd.resolve("zmq_server_public.key"));
            c.zmqPublic = key(zd.resolve("zmq_" + identity + "_public.key"));
            c.zmqSecret = key(zd.resolve("zmq_" + identity + "_secret.key"));
        }
        BufferedWriter out = null;
        if (report != null) {
            out = Files.newBufferedWriter(Paths.get(report), StandardCharsets.UTF_8,
                StandardOpenOption.CREATE, StandardOpenOption.APPEND);
            final BufferedWriter w = out;
            c.report = line -> {
                synchronized (w) {   // the load and subscriber threads both report
                    try {
                        w.write(line);
                        w.newLine();
                        w.flush();      // a crashed client still leaves every finished op
                    } catch (IOException e) {
                        throw new UncheckedIOException(e);
                    }
                }
            };
        }

        Handheld h = new Handheld(c);
        final BufferedWriter reportOut = out;
        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            h.stop();
            if (reportOut != null) {
                synchronized (reportOut) {
                    try { reportOut.close(); } catch (IOException ignored) { }
                }
            }
            System.out.println("handheld: done " + h.counters());
            System.out.flush();
        }));
        try {
            h.start();
        } catch (RuntimeException e) {
            System.err.println("handheld: start failed: " + e.getMessage());
            System.exit(4);
        }
        System.out.println("handheld: " + identity + " -> station " + station + ", subscribed to " + c.subEndpoint);
        // monotonic: a wall-clock step (NTP, WSL2) must not cut a timed run short
        long end = System.nanoTime() + duration * 1_000_000_000L;
        while (duration <= 0 || System.nanoTime() - end < 0) {
            long left = duration <= 0 ? 2000 : (end - System.nanoTime()) / 1_000_000;
            Thread.sleep(Math.min(2000, Math.max(1, left)));
            System.out.println("handheld: " + h.counters());
            String err = h.counters().lastError.get();
            if (!err.isEmpty()) System.out.println("handheld: last error: " + err);
        }
        System.exit(0);   // runs the shutdown hook -> stop() + the "done" line
    }
}
