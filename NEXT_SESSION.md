# Next session

`README.md`'s "Known gaps" section is the live, authoritative list of
feature/perf gaps. `initiatives/README.md` is the backlog/scoping-doc index —
open items that used to accumulate in this file now live there instead;
this file stays a short handoff note, not an archive.

## Resolved 2026-08-23: `third_party/asio` vendoring gap

Was: `third_party/asio` missing `asio/detail/bind_handler.hpp`, breaking
anything that `#include`s `crow.h` in the Docker image (9 tests red:
`test_stage11_soap.py`, `test_stage12_rest.py`, `test_consumer_example.py`,
`test_stage14.py`, and two Crow-server cases in
`test_message_versioning_capability_http.py`). Diffing the vendored tree
against the pinned upstream tag (`asio-1-30-2`, per
`third_party/asio/VENDORED.md`) showed 5 missing headers, not just the one
found earlier: `asio/bind_allocator.hpp`, `asio/bind_cancellation_slot.hpp`,
`asio/bind_executor.hpp`, `asio/bind_immediate_executor.hpp`, and
`asio/detail/bind_handler.hpp`. Re-vendored all five from the same tag;
confirmed in the real Docker toolchain that all 9 tests now pass and the
full suite shows no regressions (158 passed, 2 opt-in-skipped).
