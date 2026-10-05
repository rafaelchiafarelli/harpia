## WS-Discovery responder advertising the Python SOAP endpoint

- **Depends on:** `py-transports-http` task 3.
- **Contract:**
  - `harpia_runtime/wsdiscovery.py`, a port of
    `SdcAdapter/runtime/harpia_wsdiscovery.h`: a UDP responder on
    multicast `239.255.255.250:3702`.
    - It parses inbound `Probe` (types/scopes selectors) and unicast
      `Resolve` (target EPR).
    - It answers `ProbeMatches`/`ResolveMatches` SOAP 1.2 envelopes whose
      `XAddrs` carry the SOAP URL, with the fixed generic type
      `dpws:Device`.
    - It parses with stdlib XML under the same entity-expansion bound as
      `py-transports-http` task 3.
  - Generated `harpia_generated/sdc/<name>_<hash>_sdc.py` per table-bearing
    message: the participant descriptor, the scope
    `https://harpia.dev/sdc/scope/<project>/<message>`, the deterministic
    UUID5 EPR (reuse `SdcAdapter`'s namespace constant and minting **by
    import**), and `register_<name>_wsdiscovery(responder, soap_url)`.
- **Bar:** a probe answered by the Python responder is byte-equivalent
  (modulo message ids) to the C++ responder's for the same message and
  URL. The existing `UnitTests/wsdiscovery_harness.py` client finds a
  Python-advertised endpoint.
- **Out of scope:** the BICEPS participant model and a FHIR façade (C++
  has neither; `../../../README.md` §6).
- **Tests:** mirroring `test_wsdiscovery_responder.py` /
  `test_wsdiscovery_harness.py` against the Python responder: probe match,
  scope filter, resolve, and an unrelated probe gets no answer.
