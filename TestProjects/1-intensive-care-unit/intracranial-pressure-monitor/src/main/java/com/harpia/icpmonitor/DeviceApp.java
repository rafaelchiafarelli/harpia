package com.harpia.icpmonitor;

import com.harpia.generated.*;
import com.harpia.runtime.json.HarpiaJson;

/**
 * Constructs each outbound message the Intracranial Pressure (ICP) Monitor publishes and prints it
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
            icp_reading.Builder b_icp_reading = icp_reading.newBuilder();
            b_icp_reading.setPatientId("PT-ICU-04");
            b_icp_reading.setMeanIcpMmhg((float) jitter(11, 2));
            b_icp_reading.setWaveformSample((float) jitter(11, 3));
            System.out.println("icp_reading: " + HarpiaJson.toJson(b_icp_reading.build()));

            icp_threshold_alert.Builder b_icp_threshold_alert = icp_threshold_alert.newBuilder();
            b_icp_threshold_alert.setUpperBoundMmhg((float) jitter(20, 0));
            b_icp_threshold_alert.setCurrentMmhg((float) jitter(12, 3));
            b_icp_threshold_alert.setBreached((int) Math.round(jitter(0, 0)));
            System.out.println("icp_threshold_alert: " + HarpiaJson.toJson(b_icp_threshold_alert.build()));

            Thread.sleep(200);
        }
        System.out.println("Intracranial Pressure (ICP) Monitor device app: done");
    }
}
