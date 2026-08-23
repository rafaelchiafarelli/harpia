# Next session

`README.md`'s "Known gaps" section is the live, authoritative list of
feature/perf gaps. `plans/README.md` is the backlog/scoping-doc index —
open items that used to accumulate in this file now live there instead;
this file stays a short handoff note, not an archive.

## Open: `third_party/asio` vendoring gap

Discovered while verifying the capability handshake's REST/SOAP slice
(message-versioning, shipped 2026-08-22/23 — see `message/CLAUDE.md`,
`Capability/CLAUDE.md`, and the three `*CapabilityAdapter/CLAUDE.md`
files for what shipped, since the plan doc itself is gone):
`third_party/asio` is missing `asio/detail/bind_handler.hpp`. Anything
that `#include`s `crow.h` (which pulls in `asio.hpp`) fails to compile in
the harpia Docker image as a result. Confirmed **pre-existing** (via
`git stash` against a clean checkout, before that week's work started)
and unrelated to message-versioning. Currently blocks:
`test_stage11_soap.py`, `test_stage12_rest.py` (both),
`test_consumer_example.py` (both), `test_stage14.py` (both), and the two
Crow-server cases in `test_message_versioning_capability_http.py`. Worth
a dedicated session: figure out how `third_party/asio` was originally
vendored (a single-file omission from a real standalone-asio release,
most likely) and re-vendor it properly. Fixing it would turn 9 currently-
red tests green with no other code changes needed.
