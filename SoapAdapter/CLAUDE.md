# SoapAdapter — the hand-written SOAP envelope-parse runtime

**Not a generator stage.** SOAP codegen lives in `Database/SoapAdapter.py`
(+ `Database/templates/soap.h.tmpl`, `Database/auth_gate.py`,
`Database/WsdlAdapter.py`) — see `Database/CLAUDE.md`. This directory holds
only the one hand-written runtime header that generation *ships*, the same
way `XmlAdapter/runtime/harpia_xml.h` is shipped by `XmlAdapter`.

## Files
- `runtime/harpia_soap.h` — `namespace harpia::soap`. The transport-free,
  DB-free, auth-free part of the SOAP endpoint: `detail::{local_name,
  find_child, child_text}` (namespace-prefix-aware XML helpers, moved here
  from an inline block that used to be emitted into every `*_soap.h` under
  `#ifndef HARPIA_SOAP_DETAIL`), `struct Request {operation, op}`,
  `parse_envelope(str, XMLDocument*)` (step 1: well-formed XML?),
  `find_operation(const XMLDocument&, Request*)` (step 2: `<Body>` → operation
  element → local name), and `message_from_request(str, Message*)` (the pure
  set/update decode: `parse_envelope` → `find_operation` →
  `harpia::xml::from_xml_element`). `#include`s `tinyxml2.h` +
  `xml/harpia_xml.h`.

## Why it exists
static-fuzz-ci task 4a. The generated crow handler in `soap.h.tmpl` had the
envelope parse welded inline with the auth guards and CRUDL dispatch — no
standalone string→message entry point to unit-test or fuzz. Extracting it
here lets `UnitTests/test_fuzz_parsers.py` (task 4b) fuzz the **real** parse
path (`message_from_request`), and the handler is now a thin caller
(`parse_envelope` → `{auth_guard_early}` → `find_operation` →
`{auth_guard_op}` → dispatch), so the two cannot drift.

## Touchpoints
- Shipped by `Database/SoapAdapter.py` (`copy_if_different` into
  `generated/cpp/soap/`, `SOAP_RUNTIME` / `_SOAP_RUNTIME_SRC`).
- `#include`d by every generated `<name>_<hash>_soap.h` and by the
  `_SOAP_FLAT_HELPER` auth helper (`Database/auth_gate.py`).
- Skipped by `UnitTests/run_pipeline.py`'s `_collect_soap` snapshot (static
  repo runtime — same convention as `harpia_xml.h`).
- Depends on: `third_party/tinyxml2`, `XmlAdapter/runtime/harpia_xml.h`,
  protobuf `Message`.
