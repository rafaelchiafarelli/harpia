package com.harpia.android_consumer;

import static org.junit.Assert.assertNotNull;

import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;

import com.harpia.generated.users_ServiceGrpc;

import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import io.grpc.android.AndroidChannelBuilder;
import io.grpc.okhttp.OkHttpChannelBuilder;

import org.junit.Test;
import org.junit.runner.RunWith;

/**
 * Session J.26 -- verifies a gRPC client built with the Android-specific
 * transport (grpc-android + grpc-okhttp, additive to J.3's generated
 * stub classes, not a replacement) can be constructed and used against a
 * generated server ON AN ACTUAL ANDROID DEVICE/EMULATOR.
 *
 * NOT RUN, NOT VERIFIED -- same caveat as MessageClassesAndroidTest, and
 * a second, independent one specific to this file: the exact
 * io.grpc.android.AndroidChannelBuilder API shape (`usingBuilder(...)
 * .context(...).build()`) is reproduced from documentation/memory, not
 * compiled here -- confidence is lower than for MessageClassesAndroidTest
 * or ZmqClientAndroidTest, which only touch protobuf-java/JeroMQ APIs
 * this thread's other (JDK-gated, if not Android-gated) tests already
 * exercise successfully. This test only proves the CLIENT constructs; it
 * doesn't call a live server (none is available to stand up here either)
 * -- see initiatives/multi-language-targets/thread-1-java-target/
 * histories/Android-consumption/android-verification-gRPC-client.md.
 */
@RunWith(AndroidJUnit4.class)
public class GrpcClientAndroidTest {

    @Test
    public void grpcAndroidClientConstructsAgainstGeneratedStub() {
        // 10.0.2.2 is the standard Android-emulator alias for the host
        // machine's loopback interface -- a real verification pass would
        // run a generated server on the host, listening there.
        ManagedChannelBuilder<?> delegate =
            OkHttpChannelBuilder.forAddress("10.0.2.2", 50051).usePlaintext();
        ManagedChannel channel = AndroidChannelBuilder.usingBuilder(delegate)
            .context(InstrumentationRegistry.getInstrumentation().getTargetContext())
            .build();
        try {
            users_ServiceGrpc.users_ServiceBlockingStub stub =
                users_ServiceGrpc.newBlockingStub(channel);
            assertNotNull(stub);
        } finally {
            channel.shutdownNow();
        }
    }
}
