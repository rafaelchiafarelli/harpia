// Java variant of the PUB/SUB fan-out subscriber (transport-multipeer-
// coverage task 6) -- proves a Java copy is just another fan-out peer
// alongside any number of the C++ `subscriber` binary, the same
// cross-language interoperability UnitTests/test_zmq_xlang_pubsub_fanout.py
// proves structurally. See ../../src/subscriber.cpp for the C++ twin and
// ../../README.md for how to run this alongside it.
//
//   java -cp <classpath> com.harpia.fanout.Subscriber [endpoint]
//     endpoint  default tcp://127.0.0.1:5561, must match `publisher`
package com.harpia.fanout;

import com.harpia.generated.pump_tick;
import com.harpia.generated.zmq.pump_tick_zmq;
import com.harpia.runtime.zmq.HarpiaZmq;
import org.zeromq.ZContext;

public class Subscriber {
    public static void main(String[] args) throws Exception {
        String endpoint = args.length > 0 ? args[0] : "tcp://127.0.0.1:5561";

        try (ZContext ctx = new ZContext()) {
            HarpiaZmq.Receiver sub = pump_tick_zmq.newSubscriber(ctx, endpoint);
            sub.socket().setReceiveTimeOut(10000);
            System.out.println("subscriber: connected to " + endpoint);

            for (;;) {
                pump_tick.Builder b = pump_tick.newBuilder();
                if (!sub.receive(b)) {
                    System.out.println("subscriber: no tick for 10s, exiting");
                    break;
                }
                pump_tick msg = b.build();
                System.out.println("subscriber: received sequence=" + msg.getSequence()
                    + " rate_mhz=" + msg.getRateMhz());
            }
        }
    }
}
