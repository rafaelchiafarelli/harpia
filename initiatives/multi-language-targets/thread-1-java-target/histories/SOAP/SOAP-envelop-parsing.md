### Session J.15 — SOAP envelope parsing

- **Depends on:** J.10, J.11 (XML runtime), J.12 (HTTP server) merged.
- **Deliverable:** the same hand-rolled envelope get/set/update/delete
  parsing `Database/SoapAdapter.py` already does in C++ (harpia's SOAP
  was never a real SOAP/WS-* stack even there — see `Database/CLAUDE.md`),
  ported over the new Java XML runtime. Java's SOAP story (JAX-WS removed
  from the JDK since 11) doesn't matter here — no extra dependency needed.
- **Tests:**
  - Unit: envelope parsing for each operation (get/set/update/delete).

## Implementation notes (landed 2026-08-23, together with J.16)

New `JavaSoapAdapter/runtime/SoapHelpers.java`: a direct port of the C++
template's `detail::` namespace (`local_name`/`find_child`/`child_text`)
onto `org.w3c.dom` (the DOM type `HarpiaXml` already uses — no new XML
library). Response status codes ported faithfully from the C++ template,
not re-decided: 401 for auth failure, 400 for a malformed envelope, 200
for everything else INCLUDING a "not found"/"unknown operation" Fault body
(the C++ template never sets a different code for those). Full rationale
in `JavaSoapAdapter/CLAUDE.md`.

Tests landed as part of `tests/test_java_soap.py` (covers J.15/J.16
together) — see J.16's own notes for why.