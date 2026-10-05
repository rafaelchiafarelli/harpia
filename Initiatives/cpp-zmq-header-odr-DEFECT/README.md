# Two generated ZMQ headers can't share a translation unit — DEFECT

**Status: scoped, not started.** Found 2026-10-04 (python-target
`tri-language-interop/1`; decisions log item 43 in
`Initiatives/python-target/NEXT_SESSION.md`). Not fixed: it moves `golden/`.

## What was found

`ZmqAdapter/templates/header.h.tmpl` (~line 58) emits

```cpp
inline std::string runtime_origin_id() { ... }
```

into **every** `zmq/<name>_<hash>_zmq.h`, in `namespace harpia::zmq_transport`.
Including two of them in one `.cpp` (any program that uses two ZMQ message
types) fails: *redefinition of `runtime_origin_id()`*. `inline` doesn't help
within one TU — the same definition appears twice textually. (Shared CURVE
types already avoid this with a `HARPIA_ZMQ_CURVE_KEYS_DEFINED` guard; this
function has none.)

The tri-language test works around it by building one C++ binary per message.

## Scope

One epic: **`zmq-shared-runtime`**. **Moves `UnitTests/golden/zmq/`.** See
`epics/README.md`.
