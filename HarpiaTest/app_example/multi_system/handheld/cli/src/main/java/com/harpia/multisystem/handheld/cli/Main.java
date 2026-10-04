package com.harpia.multisystem.handheld.cli;

import com.harpia.multisystem.handheld.Handheld;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;

/**
 * JVM launcher for {@link Handheld} -- the same core the Android app runs.
 * Flags mirror edge's:
 *
 * <pre>
 *   handheld --station host:port --certs DIR --identity NAME --sub tcp://edge:5556
 *            --zmq-keys DIR [--authority NAME] [--notes-every N]
 *            [--list-every MS] [--id-base N] [--duration S]
 * </pre>
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

    public static void main(String[] args) throws Exception {
        String station = "127.0.0.1:50051", certs = ".", identity = "handheld", zmqKeys = ".";
        Handheld.Config c = new Handheld.Config();
        int duration = 0;
        try {
            for (int i = 0; i < args.length; i += 2) {
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
                    default: throw new IllegalArgumentException("unknown argument " + args[i]);
                }
            }
            if (c.subEndpoint == null) throw new IllegalArgumentException("--sub is required");
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
        c.zmqServerPublic = key(zd.resolve("zmq_server_public.key"));
        c.zmqPublic = key(zd.resolve("zmq_" + identity + "_public.key"));
        c.zmqSecret = key(zd.resolve("zmq_" + identity + "_secret.key"));

        Handheld h = new Handheld(c);
        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            h.stop();
            System.out.println("handheld: done " + h.counters());
            System.out.flush();
        }));
        h.start();
        System.out.println("handheld: " + identity + " -> station " + station + ", subscribed to " + c.subEndpoint);
        long end = duration > 0 ? System.currentTimeMillis() + duration * 1000L : Long.MAX_VALUE;
        while (System.currentTimeMillis() < end) {
            Thread.sleep(Math.min(2000, Math.max(1, end - System.currentTimeMillis())));
            System.out.println("handheld: " + h.counters());
            String err = h.counters().lastError.get();
            if (!err.isEmpty()) System.out.println("handheld: last error: " + err);
        }
        System.exit(0);   // runs the shutdown hook -> stop() + the "done" line
    }
}
