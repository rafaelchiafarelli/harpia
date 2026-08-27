package com.harpia.bladderscanner;

import com.harpia.generated.*;
import com.harpia.runtime.json.HarpiaJson;

/**
 * Constructs each outbound message the Bladder Scanner publishes and prints it
 * as JSON. Extend with the generated gRPC / ZMQ clients as in
 * HarpiaTest/app_example/android_consumer.
 *
 * <p>Consumes harpia's Java-target output as a black box -- build a project from
 * this folder with HARPIA_GEN_LANG=java first (see README.md). Generated message
 * classes land in the flat package {@code com.harpia.generated} with their
 * name kept verbatim ({@code vital_signs.newBuilder()}); {@code HarpiaJson}
 * is the generated JSON runtime helper (same one HarpiaTest/app_example/android_consumer uses).
 */
public final class DeviceApp {
    private static final java.util.Random RNG = new java.util.Random(20260825L);

    private static double jitter(double mean, double sd) {
        return sd <= 0.0 ? mean : mean + RNG.nextGaussian() * sd;
    }

    public static void main(String[] args) throws Exception {
        int iterations = 1;
        for (int i = 0; i < iterations; i++) {
            bladder_scan_result.Builder b_bladder_scan_result = bladder_scan_result.newBuilder();
            b_bladder_scan_result.setPatientId("PT-WARD-04");
            b_bladder_scan_result.setBladderVolumeMl((float) jitter(250, 40));
            b_bladder_scan_result.setQualityRating((int) Math.round(jitter(4, 0)));
            b_bladder_scan_result.setOutlineThumbnailId("THMB-001");
            System.out.println("bladder_scan_result: " + HarpiaJson.toJson(b_bladder_scan_result.build()));

            Thread.sleep(200);
        }
        System.out.println("Bladder Scanner device app: done");
    }
}
