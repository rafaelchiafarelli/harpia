package com.harpia.anesthesia;

import com.harpia.generated.*;
import com.harpia.runtime.json.HarpiaJson;

/**
 * Simulates normal human and operator behaviour for the Anesthesia Machine,
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
            agent_delivery.Builder b_agent_delivery = agent_delivery.newBuilder();
            b_agent_delivery.setIsofluranePercent((float) jitter(1.2, 0.1));
            b_agent_delivery.setSevofluranePercent((float) jitter(0.2, 0.05));
            b_agent_delivery.setOxygenMixPercent((float) jitter(50, 3));
            System.out.println("agent_delivery: " + HarpiaJson.toJson(b_agent_delivery.build()));

            agent_depletion_warning.Builder b_agent_depletion_warning = agent_depletion_warning.newBuilder();
            b_agent_depletion_warning.setAgentName("sevoflurane");
            b_agent_depletion_warning.setRemainingPercent((float) jitter(60, 5));
            System.out.println("agent_depletion_warning: " + HarpiaJson.toJson(b_agent_depletion_warning.build()));

            ventilation_loop.Builder b_ventilation_loop = ventilation_loop.newBuilder();
            b_ventilation_loop.setPressureSample((float) jitter(15, 4));
            b_ventilation_loop.setVolumeSample((float) jitter(400, 30));
            System.out.println("ventilation_loop: " + HarpiaJson.toJson(b_ventilation_loop.build()));

            Thread.sleep(200);
        }
        System.out.println("Anesthesia Machine human-mock: done");
    }
}
