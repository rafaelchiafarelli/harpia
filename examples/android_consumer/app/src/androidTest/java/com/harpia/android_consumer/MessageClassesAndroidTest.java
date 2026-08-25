package com.harpia.android_consumer;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

import androidx.test.ext.junit.runners.AndroidJUnit4;

import com.harpia.generated.users;
import com.harpia.runtime.json.HarpiaJson;

import org.junit.Test;
import org.junit.runner.RunWith;

/**
 * Session J.25 -- verifies harpia-generated message classes (protobuf-java
 * POJOs+builders) and JSON (de)serialization construct/round-trip
 * correctly ON AN ACTUAL ANDROID DEVICE/EMULATOR, not just the desktop/
 * server JVM every other Java-target test in this thread runs against.
 *
 * NOT RUN, NOT VERIFIED -- this environment has no Android SDK/emulator
 * at all. See ../../../../../../README.md (this module's own) for the
 * full caveat, and initiatives/multi-language-targets/thread-1-java-
 * target/histories/Android-consumption/android-verification-message-
 * classes.md for this session's own history.
 */
@RunWith(AndroidJUnit4.class)
public class MessageClassesAndroidTest {

    @Test
    public void messageClassConstructsAndReadsBackOnDevice() {
        users msg = users.newBuilder()
            .setAddress("wonderland")
            .setName("alice")
            .build();
        assertEquals("wonderland", msg.getAddress());
        assertEquals("alice", msg.getName());
    }

    @Test
    public void jsonRoundTripWorksOnDevice() throws Exception {
        users msg = users.newBuilder()
            .setAddress("wonderland")
            .setName("alice")
            .build();
        String json = HarpiaJson.toJson(msg);
        assertTrue(json.contains("wonderland"));

        users.Builder back = users.newBuilder();
        HarpiaJson.fromJson(json, back);
        assertEquals(msg, back.build());
    }
}
