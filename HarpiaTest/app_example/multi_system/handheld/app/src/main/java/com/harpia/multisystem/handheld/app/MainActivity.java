package com.harpia.multisystem.handheld.app;

import android.app.Activity;
import android.content.res.AssetManager;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import android.widget.TextView;

import com.harpia.multisystem.handheld.Handheld;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.Properties;

/**
 * One screen: starts {@link Handheld} (the same core the JVM CLI runs) with the
 * certificates and keys bundled as assets, and shows its counters. All logic
 * lives in core/.
 */
public final class MainActivity extends Activity {
    static final String TAG = "harpia-handheld";

    private final Handler ui = new Handler(Looper.getMainLooper());
    private Handheld handheld;
    private TextView view;

    private byte[] asset(AssetManager a, String name) throws IOException {
        try (InputStream in = a.open(name); ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            byte[] buf = new byte[4096];
            int n;
            while ((n = in.read(buf)) > 0) out.write(buf, 0, n);
            return out.toByteArray();
        }
    }

    private String text(AssetManager a, String name) throws IOException {
        return new String(asset(a, name), StandardCharsets.US_ASCII).trim();
    }

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        view = new TextView(this);
        view.setTextSize(18);
        view.setPadding(32, 32, 32, 32);
        setContentView(view);
        // network I/O must stay off the main thread
        new Thread(this::startCore, "handheld-start").start();
    }

    private void startCore() {
        try {
            AssetManager a = getAssets();
            Properties p = new Properties();
            try (InputStream in = a.open("handheld.properties")) {
                p.load(in);
            }
            Handheld.Config c = new Handheld.Config();
            c.stationHost = p.getProperty("station.host", "10.0.2.2");
            c.stationPort = Integer.parseInt(p.getProperty("station.port", "50051"));
            c.authority = p.getProperty("station.authority");
            c.subEndpoint = p.getProperty("sub.endpoint", "tcp://10.0.2.2:5556");
            c.idBase = Integer.parseInt(p.getProperty("id.base", "500000"));
            c.notesEvery = Integer.parseInt(p.getProperty("notes.every", "5"));
            c.author = "handheld-android";
            c.caPem = asset(a, "ca.pem");
            c.certPem = asset(a, "client_handheld.pem");
            c.keyPem = asset(a, "client_handheld_key.pem");
            c.zmqServerPublic = text(a, "zmq_server_public.key");
            c.zmqPublic = text(a, "zmq_handheld_public.key");
            c.zmqSecret = text(a, "zmq_handheld_secret.key");
            handheld = new Handheld(c);
            handheld.start();
            refresh();
        } catch (Exception e) {
            Log.e(TAG, "start failed", e);
            ui.post(() -> view.setText("start failed: " + e.getMessage()));
        }
    }

    private void refresh() {
        ui.post(() -> {
            if (handheld == null) return;
            Handheld.Counters k = handheld.counters();
            String s = "samples received: " + k.samplesReceived.get()
                + "\nnotes written: " + k.notesWritten.get()
                + "\nreadings listed: " + k.readingsListed.get()
                + "\nerrors: " + k.errors.get()
                + "\nlast error: " + k.lastError.get();
            view.setText(s);
            Log.i(TAG, "handheld: " + k);
            ui.postDelayed(this::refresh, 1000);
        });
    }

    @Override
    protected void onDestroy() {
        if (handheld != null) new Thread(handheld::stop).start();
        super.onDestroy();
    }
}
