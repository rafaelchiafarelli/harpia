## Extract the SOAP envelope parse seam

Scoped 2026-09-01, mid-epic, when task 4 (SOAP fuzz target) surfaced the
shape question its own file anticipated. **Implemented 2026-09-01.**

The SOAP parse path had no standalone string→message entry point — it
lived inline in the crow HTTP handler in `Database/templates/soap.h.tmpl`,
with the `detail::{local_name,find_child,child_text}` helpers emitted
inline (`#ifndef HARPIA_SOAP_DETAIL`) into every generated `*_soap.h`.
This task extracts that seam so task 4b can fuzz the **real** parse path.
Split from task 4 per that file's own "stop and flag it as its own task"
instruction (Rafael approved the split + this task).

### Decisions (as implemented)

- **New hand-written runtime `SoapAdapter/runtime/harpia_soap.h`**
  (`namespace harpia::soap`), a new top-level `SoapAdapter/` module dir
  (`CLAUDE.md` added). Copied verbatim into `generated/cpp/soap/` by
  `SoapAdapter.Process()` via `copy_if_different` — the
  `XmlAdapter`/`harpia_xml.h` pattern (`SOAP_RUNTIME` + `_SOAP_RUNTIME_SRC`
  module constants). It carries:
  - `detail::local_name` / `detail::find_child` / `detail::child_text`
    (moved verbatim from the template; `local_name` also got a `nullptr`
    guard),
  - `struct Request { std::string operation; const tinyxml2::XMLElement* op; }`,
  - `bool parse_envelope(const std::string&, tinyxml2::XMLDocument*)` —
    step 1, well-formed XML? (HTTP 400 when false; the non-hardened
    handler runs its credential check *between* this and `find_operation`,
    which is why they are two calls, not one),
  - `bool find_operation(const tinyxml2::XMLDocument&, Request*)` — step 2,
    `<Body>` → operation element → local name (HTTP 400 when absent),
  - `bool message_from_request(const std::string&, ::google::protobuf::Message*)`
    — the pure set/update decode: `parse_envelope` → `find_operation` →
    `harpia::xml::from_xml_element(op->FirstChildElement(), msg)`. **Task
    4b's fuzz target.**
  `#include`s `"tinyxml2.h"` + `"xml/harpia_xml.h"`.
- **`soap.h.tmpl` rewired, behavior-preserving.** Inline
  `HARPIA_SOAP_DETAIL` block deleted; `#include "soap/harpia_soap.h"`
  added. The handler's `doc.Parse(...)` + 4-line walk became
  `parse_envelope(req.body, &doc)` → `{auth_guard_early}` →
  `find_operation(doc, &soap_req)` → `{auth_guard_op}`. Exact ordering
  preserved (Parse→400, credential check, Body/op→400, dispatch); the
  per-operation bodies keep their `soap_req.op->FirstChildElement(...)`
  calls verbatim. The flat `authorized_{name}(doc)` helper and both auth
  guards are untouched — they already called `::harpia::soap::detail::`,
  now resolved from the header.
- **Golden re-blessed:** all 12 `UnitTests/golden/soap/*_soap.h` (lose the
  inline block, gain the include + the two-call parse).
  `run_pipeline.py`'s `_collect_soap` now skips `harpia_soap.h` in the
  snapshot — same convention as `_collect_xml` for `harpia_xml.h`.

### Contract

**In:** `Database/templates/soap.h.tmpl`, `Database/SoapAdapter.py`,
`XmlAdapter/runtime/harpia_xml.h` (`from_xml_element`), tinyxml2 — all
present.

**Required:** nothing from any epic. The epic's only task with a
generator-source + golden footprint (README's "no generator change" note
now scoped to tasks 1–3).

**Delivered:**
- `SoapAdapter/runtime/harpia_soap.h` + `SoapAdapter/CLAUDE.md` (new).
- `Database/SoapAdapter.py` — copies the runtime into `generated/cpp/soap/`.
- `Database/templates/soap.h.tmpl` — `#include`s it, drops the inline
  block, routes the handler parse through `parse_envelope` +
  `find_operation`.
- `UnitTests/run_pipeline.py` — `_collect_soap` skips `harpia_soap.h`.
- `UnitTests/golden/soap/*` — re-blessed (12 headers).
- `Database/CLAUDE.md` — `SoapAdapter.py` bullet updated with the seam.

**Pre-work:** none (the helpers already existed inline — a move + two new
pure wrappers + one compose function).

**Tests:** no new test. Green (Docker) before marking done:
`test_stage11_soap.py`, `test_rbac.py`, `test_sessions.py`,
`test_rest_soap_mtls.py`, `test_wsdiscovery_responder.py`,
`test_golden.py` (re-blessed). Full suite at the epic merge-up.

**Out of scope:** any change to what the SOAP endpoint *does*; WSDL /
WS-Security; the fuzz target itself (task 4b).

---
## Epic context — static-fuzz-ci

See the epic `README.md`. Task 4b (the SOAP fuzz target) depends on this
task. Tasks 1–3 are independent of it.
