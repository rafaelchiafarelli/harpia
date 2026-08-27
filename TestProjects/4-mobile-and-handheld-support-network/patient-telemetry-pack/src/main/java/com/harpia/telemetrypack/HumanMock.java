package com.harpia.telemetrypack;

import com.harpia.generated.*;
import com.harpia.runtime.json.HarpiaJson;

/**
 * Simulates normal human and operator behaviour for the Patient Telemetry Pack,
 * emitting a physiologically plausible stream of its outbound messages
 * as harpia-generated protobuf, printed as JSON.
 *
 * <p>Consumes harpia's Java-target output as a black box -- build a project from
 * this folder with HARPIA_GEN_LANG=java first (see README.md). Generated message
 * classes land in the flat package {@code com.harpia.generated} with their
 * name kept verbatim ({@code vital_signs.newBuilder()}); {@code HarpiaJson}
 * is the generated JSON runtime helper (same one HarpiaTest/app_example/android_consumer uses).
 */
public final class HumanMock {
    private static final java.util.Random RNG = new java.util.Random(20260825L);

    private static double jitter(double mean, double sd) {
        return sd <= 0.0 ? mean : mean + RNG.nextGaussian() * sd;
    }

    public static void main(String[] args) throws Exception {
        int iterations = 20;
        for (int i = 0; i < iterations; i++) {
            ambulatory_vitals.Builder b_ambulatory_vitals = ambulatory_vitals.newBuilder();
            b_ambulatory_vitals.setPatientId("PT-TELE-01");
            b_ambulatory_vitals.setHeartRateBpm((float) jitter(85, 10));
            b_ambulatory_vitals.setSpo2Percent((float) jitter(97, 1));
            b_ambulatory_vitals.setSignalStrengthDbm((float) jitter(-60, 5));
            b_ambulatory_vitals.setBatteryPercent((float) jitter(80, 0));
            System.out.println("ambulatory_vitals: " + HarpiaJson.toJson(b_ambulatory_vitals.build()));

            low_battery_alert.Builder b_low_battery_alert = low_battery_alert.newBuilder();
            b_low_battery_alert.setBatteryPercent((float) jitter(80, 0));
            System.out.println("low_battery_alert: " + HarpiaJson.toJson(b_low_battery_alert.build()));

            Thread.sleep(200);
        }
        System.out.println("Patient Telemetry Pack human-mock: done");
    }
}
