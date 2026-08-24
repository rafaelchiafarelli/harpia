### Session J.16 — SOAP acceptance gate

- **Depends on:** J.15 merged.
- **Tests:**
  - Integration: live SOAP envelope calls against the generated Java
    server, same shape as the existing C++ SOAP tests.
- **Acceptance gate:** this session is the acceptance gate.

## Implementation notes (landed 2026-08-23, together with J.15)

`tests/test_java_soap.py::test_soap_envelope_cycle_over_http` — a real
`HttpServer` on an ephemeral port, driven with `java.net.http.HttpClient`
posting real SOAP envelopes: wrong credentials get a 401 Fault; a full
set(create)/get(read)/update/delete cycle against `users`; a get after
delete comes back as a "not found" Fault at HTTP 200, matching the C++
target's own status-code choice. Not run in this environment (no gradle/
JDK here), same status as every other Java integration test this thread
has added.

Same deferred-scope note as the REST/DB acceptance gates: proves the SOAP
surface for what J.6/J.15 actually built (top-level scalar/enum columns),
not full C++ `SoapAdapter` parity.