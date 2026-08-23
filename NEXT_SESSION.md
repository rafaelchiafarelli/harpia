# Next session

`README.md`'s "Known gaps" section is the live, authoritative list of
feature/perf gaps. `plans/README.md` is the backlog/scoping-doc index —
open items that used to accumulate in this file now live there instead;
this file stays a short handoff note, not an archive.

## message-versioning: all real work shipped (2026-08-22/23)

`plans/message-versioning.md` §3 (Foundation), §4 (Parse-boundary
hardening), and §5 (capability handshake, all four transports — gRPC,
REST/SOAP, ZMQ) are done. §6 is a cross-reference note, not a task. §9's
open questions are both now resolved/updated in place — there is nothing
left to do in this plan except the separate item below. Read
`plans/message-versioning.md` §10–§13 if picking this back up, for the
full "what shipped and why" record, including one real correction found
mid-work: §5's original text assumed a REST/SOAP session mechanism and a
ZMQ stream-setup phase ("Track B"/"Track C") that turned out not to exist
in the actual codebase — only in the separate, unstarted
`plans/medical_devices/` compliance plan. Built standalone alternatives
instead (§13).

## Separate, unrelated finding worth its own session: `third_party/asio` vendoring gap

Discovered while verifying the capability handshake's REST/SOAP slice:
`third_party/asio` is missing `asio/detail/bind_handler.hpp`. Anything
that `#include`s `crow.h` (which pulls in `asio.hpp`) fails to compile in
the harpia Docker image as a result. Confirmed **pre-existing** (via
`git stash` against a clean checkout, before any message-versioning work
started this week) and unrelated to that plan. Currently blocks:
`test_stage11_soap.py`, `test_stage12_rest.py` (both), `test_consumer_example.py`
(both), `test_stage14.py` (both), and the two Crow-server cases in the new
`test_message_versioning_capability_http.py`. Not fixed as part of
message-versioning (out of scope, deliberately) — worth a dedicated
session: figure out how `third_party/asio` was originally vendored (a
single-file omission from a real standalone-asio release, most likely)
and re-vendor it properly. Fixing it would turn 9 currently-red tests
green with no other code changes needed.

## Session-management note

This file no longer describes an active handoff — §3 through all of §5
shipped in one continuous conversation (not handed off between sessions).
Whoever picks up either item above should still read the relevant plan
doc in full first, the same as any fresh start would.
