package com.harpia.patientmonitor;

import com.harpia.generated.*;
import com.harpia.runtime.json.HarpiaJson;

/**
 * Constructs each outbound message the Multiparameter Patient Monitor publishes and prints it
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
            vital_signs.Builder b_vital_signs = vital_signs.newBuilder();
            b_vital_signs.setPatientId("PT-ICU-01");
            b_vital_signs.setHeartRateBpm((float) jitter(78, 6));
            b_vital_signs.setSpo2Percent((float) jitter(97, 1.5));
            b_vital_signs.setRespirationRateBpm((float) jitter(16, 2));
            b_vital_signs.setBpSystolicMmhg((float) jitter(120, 8));
            b_vital_signs.setBpDiastolicMmhg((float) jitter(78, 6));
            System.out.println("vital_signs: " + HarpiaJson.toJson(b_vital_signs.build()));

            monitor_alarm.Builder b_monitor_alarm = monitor_alarm.newBuilder();
            b_monitor_alarm.setPatientId("PT-ICU-01");
            b_monitor_alarm.setAlarmCode((int) Math.round(jitter(0, 0)));
            b_monitor_alarm.setSeverity((int) Math.round(jitter(1, 0)));
            b_monitor_alarm.addWarningFlags("nominal");
            System.out.println("monitor_alarm: " + HarpiaJson.toJson(b_monitor_alarm.build()));

            Thread.sleep(200);
        }
        System.out.println("Multiparameter Patient Monitor device app: done");
    }
}
