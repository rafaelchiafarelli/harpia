# doxygen-generation — epics

One epic: **doc-comment-coverage** (`doc-comment-coverage/tasks/`).

`../doxygen-generation.md`'s status note explains why only one body of
work is left: **F6** (the mechanical Doxyfile / CMake target /
`Doxygen/mainpage.py` plumbing, plus the gated
`UnitTests/test_doxygen_docs.py` zero-warnings check) already shipped and
merged to `dev` on 2026-08-23 — see
`../../medical_devices/epics/foundation-handoff.md`'s F6 section. What
remains is `../doxygen-generation.md` §3/§4: real, per-template Doxygen
doc-comments (not generic boilerplate) landing in the consumer-facing
headers the generator emits, plus a golden-style snapshot test per landed
comment (§6).

## Why this is a *fallback* epic

Ground Rule 6 says this work is supposed to happen incrementally, inside
whichever `medical_devices` epic next touches a given adapter / template —
not as a separate deferred effort. That is still the preferred path: a
task in db-encryption, transport-authn, serialization, etc. that touches
`CrudlAdapter` / `XmlAdapter` / `ZmqAdapter` / etc. should land the
matching doc-comment in the same sitting, per that epic's Definition of
Done.

This epic exists for two things Ground Rule 6 alone doesn't cover:

1. **A checklist.** Without it, "did the doc-comment land" is only
   answerable by re-reading every other epic's diffs. The tasks below
   double as that checklist — one per adapter / template group,
   cross-referencing which `medical_devices` epic is expected to cover it.
2. **An owner for gaps.** Some templates (`ProtoFile/FileCreator.py`'s
   message / field templates, the shared generated-file banner) aren't in
   *any* `medical_devices` epic's Files-touched list — nobody's task will
   land them opportunistically. This epic is where those get done directly.

**Before picking up any task:** check whether the "expected covered by"
epic named in it already merged the work (`git log`, that epic's
`ComplianceReport/` note, or a grep for the doc-comment text). Only do it
here if it hasn't landed, or if the task says no other epic is expected to
cover it.

## Task order

Tasks are independent (different files) except the closing sweep:

```
shared-generated-file-banner  ─┐  all independent, any order / parallel
message-class-comments         │
field-modifier-comments        │
json-xml-adapter-comments      │
database-dao-comments          │
zmq-adapter-comments          ─┘
              │
              ▼
closing-sweep-and-status   (needs the six above, or their Ground-Rule-6
                            equivalents elsewhere, merged)
```

## Definition of done (every task)

- The doc-comment's *content* matches the specific pitfall text in
  `../doxygen-generation.md` §4 (or the task's own description) — not
  generic boilerplate copy-pasted across templates.
- A golden-style snapshot test (mirroring `test_golden.py`) asserting that
  specific content, per `../doxygen-generation.md` §6, so a later refactor
  can't silently regress it back to boilerplate without a test noticing.
- If the work surfaces a consumer-relevant pitfall not already in
  `../doxygen-generation.md` §4, add a row there in the same task.

## Watch for

- Don't duplicate work another epic already did under Ground Rule 6 — see
  "Why this is a fallback epic" above.
- `WsdlAdapter` (in `database-dao-comments`) has no clearly expected owner
  among the current `medical_devices` epics — flag it again if you pick it
  up and nothing has changed.
- `closing-sweep-and-status` checks that each of the other six actually
  happened (here or as a Ground-Rule-6 equivalent in another epic) before
  it can be treated as done.
