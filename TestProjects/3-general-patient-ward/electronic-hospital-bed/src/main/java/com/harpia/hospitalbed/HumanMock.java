package com.harpia.hospitalbed;

import com.harpia.generated.*;
import com.harpia.runtime.json.HarpiaJson;

/**
 * Simulates normal human and operator behaviour for the Electronic Hospital Bed,
 * emitting a physiologically plausible stream of its outbound messages
 * as harpia-generated protobuf, printed as JSON.
 *
 * <p>Consumes harpia's Java-target output as a black box -- build a project from
 * this folder with HARPIA_GEN_LANG=java first (see README.md). Generated message
 * classes land in the flat package {@code com.harpia.generated} with their
 * name kept verbatim ({@code vital_signs.newBuilder()}); {@code HarpiaJson}
 * is the generated JSON runtime helper (same one examples/android_consumer uses).
 */
public final class HumanMock {
    private static final java.util.Random RNG = new java.util.Random(20260825L);

    private static double jitter(double mean, double sd) {
        return sd <= 0.0 ? mean : mean + RNG.nextGaussian() * sd;
    }

    public static void main(String[] args) throws Exception {
        int iterations = 20;
        for (int i = 0; i < iterations; i++) {
            bed_status.Builder b_bed_status = bed_status.newBuilder();
            b_bed_status.setElevationAngleDeg((float) jitter(30, 5));
            b_bed_status.setLeftRailUp((int) Math.round(jitter(1, 0)));
            b_bed_status.setRightRailUp((int) Math.round(jitter(1, 0)));
            b_bed_status.setScaleWeightKg((float) jitter(78, 0.5));
            System.out.println("bed_status: " + HarpiaJson.toJson(b_bed_status.build()));

            bed_exit_alert.Builder b_bed_exit_alert = bed_exit_alert.newBuilder();
            b_bed_exit_alert.setPatientId("PT-WARD-01");
            b_bed_exit_alert.setActive((int) Math.round(jitter(0, 0)));
            System.out.println("bed_exit_alert: " + HarpiaJson.toJson(b_bed_exit_alert.build()));

            Thread.sleep(200);
        }
        System.out.println("Electronic Hospital Bed human-mock: done");
    }
}
