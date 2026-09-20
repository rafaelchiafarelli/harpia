// Java variant of the PUSH/PULL load-balance worker (transport-multipeer-
// coverage task 6) -- proves a Java copy takes a real share of the work
// alongside any number of the C++ `worker` binary, the same cross-language
// interoperability UnitTests/test_zmq_xlang_pushpull_loadbalance.py proves
// structurally. See ../../src/worker.cpp for the C++ twin and
// ../../README.md for how to run this alongside it.
//
//   java -cp <classpath> com.harpia.fanout.Worker [endpoint]
//     endpoint  default tcp://127.0.0.1:5571 -- this copy's OWN port, must
//               also be listed on `pusher`'s argv
package com.harpia.fanout;

import com.harpia.generated.courier;
import com.harpia.generated.zmq.courier_zmq;
import com.harpia.runtime.zmq.HarpiaZmq;
import org.zeromq.ZContext;

public class Worker {
    public static void main(String[] args) throws Exception {
        String endpoint = args.length > 0 ? args[0] : "tcp://127.0.0.1:5571";

        try (ZContext ctx = new ZContext()) {
            HarpiaZmq.Receiver rcv = courier_zmq.newReceiver(ctx, endpoint);
            rcv.socket().setReceiveTimeOut(10000);
            System.out.println("worker: bound to " + endpoint);

            for (;;) {
                courier.Builder b = courier.newBuilder();
                if (!rcv.receive(b)) {
                    System.out.println("worker: no work for 10s, exiting");
                    break;
                }
                System.out.println("worker: processed " + b.getPayload());
            }
        }
    }
}
