### Session J.15 — SOAP envelope parsing

- **Depends on:** J.10, J.11 (XML runtime), J.12 (HTTP server) merged.
- **Deliverable:** the same hand-rolled envelope get/set/update/delete
  parsing `Database/SoapAdapter.py` already does in C++ (harpia's SOAP
  was never a real SOAP/WS-* stack even there — see `Database/CLAUDE.md`),
  ported over the new Java XML runtime. Java's SOAP story (JAX-WS removed
  from the JDK since 11) doesn't matter here — no extra dependency needed.
- **Tests:**
  - Unit: envelope parsing for each operation (get/set/update/delete).