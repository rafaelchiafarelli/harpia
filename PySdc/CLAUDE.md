# PySdc — the Python target's WS-Discovery responder (SDC zero-config discovery)

**Pipeline role / purpose:** python-target / py-discovery. The Python side of
`SdcAdapter/` (C++ `sdc/<name>_<hash>_sdc.h` + `harpia_wsdiscovery.h`). A
stage of `LangBackend/python.py`'s `run_python`, after `PyGrpcAdapter`.

**Entry point:** `PySdcAdapter(messages, dest, compliance).Process()` →
`None` (nothing without a table-bearing message — same filter as
`SdcAdapter`, because discovery points at that message's SOAP endpoint).

## Runtime (`runtime/wsdiscovery.py` → `harpia_runtime.wsdiscovery`)
Port of `harpia_wsdiscovery.h`: `Endpoint`, `Request` / `Kind`,
`parse_request` (via `harpia_runtime.soap.parse_envelope`: no namespace
processing, DTD/entity refused — the py-transports-http task 3 bound),
`endpoint_matches` (types ⊆, scopes by prefix, empty selector = all),
`build_match` / `build_response` (SOAP 1.2, byte-identical to C++),
`Responder` (`add`, pure `handle_datagram(bytes) -> bytes | None`,
`start(port=3702)` — UDP on `0.0.0.0`, joins `239.255.255.250` (a failed
join still answers unicast), one daemon thread polling with a 0.2 s
timeout; `stop()` joins and closes; restartable).
**Python extension:** `start(port)` takes a port (C++ is fixed to 3702) so
tests run without the well-known port.

## Generated (`harpia_generated/sdc/<name>_<hash>_sdc.py`)
`ENDPOINT_REFERENCE`, `DEVICE_TYPE`, `SCOPE` (`SdcAdapter._endpoint_reference`
/ `GENERIC_DEVICE_TYPE` / `SCOPE_PREFIX` + `_project_name`, imported — so C++
and Python builds of one schema advertise identical descriptors),
`<name>_wsdiscovery_endpoint(soap_url)`, `register_<name>_wsdiscovery(
responder, soap_url)` (XAddrs = `soap_url + "/<name>"`, as C++).

## Out of scope
BICEPS participant model, FHIR façade (C++ has neither). The static
`<name>_<hash>.wsdd.xml` sidecar stays C++-side only (it is a doc file).

## Touchpoints
- Depends on: `SdcAdapter` constants/minting, `harpia_runtime.soap`
  (copied by `PyHttpAdapter` for the same table-bearing condition).
- Tested by: `UnitTests/test_py_wsdiscovery.py` (+ `wsdiscovery_harness.py`).
