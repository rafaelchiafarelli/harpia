package com.harpia.android_consumer;

import static org.junit.Assert.assertTrue;

import androidx.test.ext.junit.runners.AndroidJUnit4;

import com.harpia.generated.courier;
import com.harpia.generated.zmq.courier_zmq;
import com.harpia.runtime.zmq.HarpiaZmq;

import org.junit.Test;
import org.junit.runner.RunWith;
import org.zeromq.ZContext;

/**
 * Session J.27 -- verifies the pure-Java JeroMQ ZMQ client (no JNI, no
 * native library -- JavaZmqAdapter/CLAUDE.md) actually runs on Android's
 * ART runtime, not just a desktop/server JVM. This is the one thing the
 * thread README flags as genuinely unconfirmed on-device specifically
 * (../../initiatives/multi-language-targets/thread-1-java-target/
 * README.md §7's ZMQ bullet).
 *
 * Track acceptance gate: per this session's own history file, this is
 * the *track's* real "done" bar (README §8) -- message classes (J.25),
 * gRPC (J.26), and ZMQ (this file) verified on-device together, not just
 * "the Java target builds and passes its own tests."
 *
 * NOT RUN, NOT VERIFIED -- same caveat as the other two files in this
 * module (no Android SDK/emulator here). Uses inproc:// deliberately, so
 * the test is self-contained (no external server/network needed) and
 * isolates exactly the fact in question -- whether JeroMQ's ZMTP
 * implementation runs on ART at all, not network reachability.
 */
@RunWith(AndroidJUnit4.class)
public class ZmqClientAndroidTest {

    @Test
    public void pushPullRoundTripWorksOnDevice() throws Exception {
        try (ZContext ctx = new ZContext()) {
            String endpoint = "inproc://android-zmq-test";
            HarpiaZmq.Receiver receiver = courier_zmq.newReceiver(ctx, endpoint);
            HarpiaZmq.Sender sender = courier_zmq.newSender(ctx, endpoint);
            Thread.sleep(100);

            courier msg = courier.newBuilder().setPayload("hello-android").build();
            assertTrue(sender.send(msg));

            courier.Builder b = courier.newBuilder();
            assertTrue(receiver.receive(b));
            assertTrue(b.getPayload().equals("hello-android"));
        }
    }
}
