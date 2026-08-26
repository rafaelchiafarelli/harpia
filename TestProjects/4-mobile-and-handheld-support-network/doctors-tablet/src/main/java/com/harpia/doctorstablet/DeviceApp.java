package com.harpia.doctorstablet;

import com.harpia.generated.*;
import com.harpia.runtime.json.HarpiaJson;

/**
 * Constructs each outbound message the Doctor's Tablet publishes and prints it
 * as JSON. Extend with the generated gRPC / ZMQ clients as in
 * examples/android_consumer.
 *
 * <p>Consumes harpia's Java-target output as a black box -- build a project from
 * this folder with HARPIA_GEN_LANG=java first (see README.md). Generated message
 * classes land in the flat package {@code com.harpia.generated} with their
 * name kept verbatim ({@code vital_signs.newBuilder()}); {@code HarpiaJson}
 * is the generated JSON runtime helper (same one examples/android_consumer uses).
 */
public final class DeviceApp {
    private static final java.util.Random RNG = new java.util.Random(20260825L);

    private static double jitter(double mean, double sd) {
        return sd <= 0.0 ? mean : mean + RNG.nextGaussian() * sd;
    }

    public static void main(String[] args) throws Exception {
        int iterations = 1;
        for (int i = 0; i < iterations; i++) {
            clinician_interaction_log.Builder b_clinician_interaction_log = clinician_interaction_log.newBuilder();
            b_clinician_interaction_log.setUserId("dr-adams");
            b_clinician_interaction_log.setAction("view-chart");
            b_clinician_interaction_log.setTargetRef("PT-ICU-01");
            System.out.println("clinician_interaction_log: " + HarpiaJson.toJson(b_clinician_interaction_log.build()));

            authorization_request.Builder b_authorization_request = authorization_request.newBuilder();
            b_authorization_request.setUserId("dr-adams");
            b_authorization_request.setScope("vitals-read");
            b_authorization_request.setTokenRef("TOK-0001");
            System.out.println("authorization_request: " + HarpiaJson.toJson(b_authorization_request.build()));

            Thread.sleep(200);
        }
        System.out.println("Doctor's Tablet device app: done");
    }
}
