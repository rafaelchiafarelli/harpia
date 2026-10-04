## SOAP endpoint — envelope-parse seam port + get/set/update/delete

- **Depends on:** task 2; `py-serialization` task 2 (`from_xml_element`).
- **Contract:**
  - `harpia_runtime/soap.py`: a port of `SoapAdapter/runtime/harpia_soap.h`
    with `local_name`, `find_child`, `child_text`, `parse_envelope`,
    `find_operation` and `message_from_request` (the pure string → message
    decode). It is namespace-prefix aware and uses stdlib
    `xml.etree.ElementTree`. **Use `defusedxml`-equivalent hardening:**
    stdlib `xml.etree` doesn't resolve external entities, but entity
    expansion (billion laughs) must be bounded. Either a size/depth limit
    before parse, or **Decision needed** to add `defusedxml` as a
    dependency.
  - Generated `harpia_generated/soap/<name>_<hash>_soap.py`,
    `register(router, pool, base)`: POST `<base>/<name>`, credentials from
    the SOAP header (flat variant), and dispatch on the Body's first child
    (`get`/`set`/`update`/`delete`).
  - Status codes ported from C++, not re-decided: 401 auth failure (with a
    Fault), 400 malformed/no message element, 200 for everything else,
    **including** not-found and unknown-operation Faults.
  - Registered by `HttpServer` (task 2). The WSDL is the existing
    language-neutral `<dest>/wsdl/<name>_<hash>.wsdl`; Python references
    it and doesn't regenerate it.
- **Bar:** a SOAP request accepted by the C++ endpoint is accepted by the
  Python one with the same response envelope.
- **Out of scope:** RBAC/session for SOAP (tasks 6–7).
- **Tests:**
  - Generated-project tests for each op + each status code.
  - A Python fuzz-style test (random/mutated envelopes against
    `message_from_request`, the `test_fuzz_parsers.py` idea) asserting
    "returns False or a message, never raises, bounded time".
