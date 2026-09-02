## Extract the SOAP envelope parse seam

Scoped 2026-09-01, mid-epic, when task 4 (SOAP fuzz target) surfaced the
shape question its own file anticipated: **the SOAP parse path has no
standalone string→message entry point.** It lives inline in the crow HTTP
handler in `Database/templates/soap.h.tmpl`, and the
`detail::{local_name,find_child,child_text}` helpers are emitted inline
(`#ifndef HARPIA_SOAP_DETAIL`) into every generated `*_soap.h`.

This task extracts that seam into a hand-written runtime header so task 4b
can fuzz **the real parse path**, not a copy of it. Split from task 4 per
the task-4 file's own "stop and flag it as its own task" instruction
(approved 2026-09-01).

### Decisions (settled during scoping — do not re-litigate)

- **New static runtime header `SoapAdapter/runtime/harpia_soap.h`**
  (`namespace harpia::soap`), copied verbatim into `generated/cpp/soap/`
  by `SoapAdapter` — exactly the `XmlAdapter` / `harpia_xml.h` pattern
  (`copy_if_different` at the top of `Process()`, a `RUNTIME` +
  `_RUNTIME_SRC` module constant). It carries:
  - `detail::local_name` / `detail::find_child` / `detail::child_text`
    (moved verbatim from the template's inline block),
  - `struct Request { std::string operation; const tinyxml2::XMLElement* op; }`,
  - `bool parse_request(const std::string& envelope, tinyxml2::XMLDocument* doc,
    Request* out)` — Parse → `RootElement` → `find_child(env,"Body")` →
    `body->FirstChildElement()` (the operation element) → `local_name`.
    Returns false on malformed XML or a missing `<Body>`/operation element
    (the exact 400 conditions the generated handler checks). No socket, no
    DB, no auth.
  - `bool message_from_request(const std::string& envelope,
    ::google::protobuf::Message* msg)` — `parse_request` then
    `harpia::xml::from_xml_element(req.op->FirstChildElement(), msg)`; the
    pure `set`/`update` decode path, and task 4b's fuzz entry point.
  It `#include`s `"tinyxml2.h"` and `"xml/harpia_xml.h"`.
- **`soap.h.tmpl` rewired, behavior-preserving.** The inline
  `HARPIA_SOAP_DETAIL` block is deleted; the header gains
  `#include "soap/harpia_soap.h"`. The handler's `doc.Parse(...)` + 4-line
  Envelope/Body/op walk becomes a `::harpia::soap::parse_request(req.body,
  &doc, &soap_req)` call; `const std::string name = soap_req.operation;`.
  The per-operation bodies keep their exact `soap_req.op->FirstChildElement(...)`
  calls (get/delete by `"id"`, set/update first-child), so the emitted
  behavior is identical. The flat-auth `authorized_{name}(doc)` helper and
  both auth guards (`{auth_guard_early}` after the parse, `{auth_guard_op}`
  after `name`) are untouched — they already call `::harpia::soap::detail::`,
  now resolved from the header.
- **Golden re-blessed.** All 12 `UnitTests/golden/soap/*_soap.h` change
  (lose the inline detail block, gain the include, the parse call).
  `run_pipeline.py`'s `_collect_soap` skips `harpia_soap.h` in the snapshot
  — same convention as `_collect_xml` for `harpia_xml.h` (static repo
  runtime, not re-snapshotted).

### Contract

**In:** `Database/templates/soap.h.tmpl`, `Database/SoapAdapter.py`,
`XmlAdapter/runtime/harpia_xml.h` (`from_xml_element`), tinyxml2 — all
present.

**Required:** nothing from any epic. This is the epic's only task with a
generator-source + golden footprint (the epic README's "no generator
change" note is now scoped to tasks 1–3).

**Delivered:**
- `SoapAdapter/runtime/harpia_soap.h` — the new hand-written runtime.
- `Database/SoapAdapter.py` — copies it into `generated/cpp/soap/`.
- `Database/templates/soap.h.tmpl` — `#include`s it, drops the inline
  detail block, routes the handler parse through `parse_request`.
- `UnitTests/run_pipeline.py` — `_collect_soap` skips `harpia_soap.h`.
- `UnitTests/golden/soap/*` — re-blessed (12 headers).
- A one-line seam note in `Database/SoapAdapter.py` / `SoapAdapter`'s
  `CLAUDE.md`.

**Pre-work:** none (the helpers already exist inline — this is a move +
one new pure function).

**Tests:** no new test. Green after this task, before marking done:
`test_stage11_soap.py`, `test_rbac.py`, `test_sessions.py`,
`test_rest_soap_mtls.py`, `test_wsdiscovery_responder.py`,
`test_golden.py` (re-blessed). Full suite at the epic merge-up.

**Out of scope:** any change to what the SOAP endpoint *does*; a WSDL /
WS-Security touch; the fuzz target itself (task 4b).

---
## Epic context — static-fuzz-ci

See the epic `README.md`. Task 4b (the SOAP fuzz target) depends on this
task. Tasks 1–3 are independent of it.
