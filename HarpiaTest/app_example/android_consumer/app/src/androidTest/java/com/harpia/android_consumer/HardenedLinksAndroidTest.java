package com.harpia.android_consumer;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

import android.content.res.AssetManager;

import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;

import com.google.protobuf.Descriptors.FieldDescriptor;
import com.harpia.generated.users;
import com.harpia.generated.users_ID;
import com.harpia.generated.users_Message;
import com.harpia.generated.users_ServiceGrpc;
import com.harpia.generated.zmq.users_zmq;
import com.harpia.runtime.grpc.HarpiaGrpcTls;
import com.harpia.runtime.grpc.HarpiaSession;
import com.harpia.runtime.zmq.HarpiaZmq;

import io.grpc.Grpc;
import io.grpc.ManagedChannel;

import org.junit.Assume;
import org.junit.Before;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.zeromq.ZContext;
import org.zeromq.ZMQ;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.Properties;
import java.util.concurrent.TimeUnit;

/**
 * multi-system-reference / java-hardened-client task 4: the first time an
 * Android client talks to a real harpia server over the network. Both links
 * the reference system's `handheld` uses, against hardened C++ servers that
 * UnitTests/run_android_hardened_servers.py runs in the emulator's container
 * (reached from the emulator as 10.0.2.2):
 *
 * <ul>
 *   <li>gRPC over grpc-okhttp with mTLS (HarpiaGrpcTls) + a bearer session
 *       (HarpiaSession): create a `users` record, read it back.</li>
 *   <li>JeroMQ SUB with CURVE, allowlisted by the C++ publisher's ZAP
 *       handler: receive the publisher's `users` stream.</li>
 * </ul>
 *
 * The server cert's SANs are localhost / 127.0.0.1 (the dev PKI), so the
 * channel dials 10.0.2.2 and verifies the cert, fully, against the CA for the
 * name "localhost" (overrideAuthority). Test-only: real deployments issue the
 * server cert for their real address (multi-system-reference reference-system
 * task 1, `--san`).
 *
 * Needs -PharpiaHardenedDir (Docker/run_android_emulator_tests.sh passes it);
 * without it every test here is skipped, not failed.
 */
@RunWith(AndroidJUnit4.class)
public class HardenedLinksAndroidTest {

    private static final String HOST = "10.0.2.2";
    private static final String CERT_NAME = "localhost";

    private AssetManager assets;
    private Properties ports;

    @Before
    public void loadConfig() throws IOException {
        assets = InstrumentationRegistry.getInstrumentation().getContext().getAssets();
        ports = new Properties();
        InputStream in;
        try {
            in = assets.open("harpia_hardened.properties");
        } catch (IOException e) {
            Assume.assumeTrue("no -PharpiaHardenedDir assets; hardened servers not running", false);
            return;
        }
        try (InputStream p = in) {
            ports.load(p);
        }
    }

    private String key(String asset) throws IOException {
        try (BufferedReader r = new BufferedReader(
                new InputStreamReader(assets.open(asset), StandardCharsets.US_ASCII))) {
            return r.readLine().trim();
        }
    }

    @Test
    public void grpcMtlsSessionCreateThenReadOnDevice() throws Exception {
        int port = Integer.parseInt(ports.getProperty("grpc.port"));
        ManagedChannel ch = Grpc.newChannelBuilderForAddress(HOST, port,
                HarpiaGrpcTls.credentials(assets.open("ca.pem"),
                                          assets.open("client.pem"),
                                          assets.open("client_key.pem")))
            .overrideAuthority(CERT_NAME)
            .build();
        try {
            HarpiaSession session = HarpiaSession.issue(ch, users_ServiceGrpc.getHeartBeatMethod());
            users_ServiceGrpc.users_ServiceBlockingStub stub = users_ServiceGrpc
                .newBlockingStub(ch)
                .withInterceptors(session.interceptor())
                .withDeadlineAfter(15, TimeUnit.SECONDS);

            int id = (int) (System.currentTimeMillis() % 1_000_000_000L);
            users.Builder u = users.newBuilder();
            FieldDescriptor idField = users.getDescriptor().findFieldByName(
                idFieldName());
            u.setField(idField, id);
            u.setField(users.getDescriptor().findFieldByName("name"), "android");

            session.withRetry(() -> stub.push(users_Message.newBuilder().setMsg(u).build()));
            users_Message back = session.withRetry(
                () -> stub.pullByID(users_ID.newBuilder().setId(id).build()));

            assertEquals("android", back.getMsg().getName());
            assertEquals(1, session.issueCount());
        } finally {
            ch.shutdownNow().awaitTermination(5, TimeUnit.SECONDS);
        }
    }

    @Test
    public void zmqCurveSubscribeFromCppPublisherOnDevice() throws Exception {
        int port = Integer.parseInt(ports.getProperty("zmq.port"));
        HarpiaZmq.CurveKeys keys = HarpiaZmq.CurveKeys.client(
            ZMQ.Curve.z85Decode(key("zmq_server_public.key")),
            ZMQ.Curve.z85Decode(key("zmq_handheld_public.key")),
            ZMQ.Curve.z85Decode(key("zmq_handheld_secret.key")));
        try (ZContext ctx = new ZContext()) {
            HarpiaZmq.Receiver sub = users_zmq.newSubscriber(ctx, "tcp://" + HOST + ":" + port, keys);
            sub.socket().setLinger(0);
            sub.socket().setReceiveTimeOut(1000);
            int received = 0;
            long end = System.currentTimeMillis() + 20_000;
            while (received < 5 && System.currentTimeMillis() < end) {
                users.Builder b = users.newBuilder();
                if (sub.receive(b) && b.getName().equals("edge")) received++;
            }
            assertTrue("received " + received + " of 5 from the C++ publisher", received >= 5);
        }
    }

    // ID_<hash>: the hidden primary-key field, hash-suffixed per project.
    private static String idFieldName() {
        for (FieldDescriptor fd : users.getDescriptor().getFields()) {
            if (fd.getName().startsWith("ID_")) return fd.getName();
        }
        throw new IllegalStateException("users has no ID_ field");
    }
}
