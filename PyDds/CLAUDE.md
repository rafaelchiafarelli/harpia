# PyDds — the Python target's DDS transport

**Pipeline role / purpose:** python-target / py-dds. The Python side of
`DdsAdapter/` (the C++ per-message `dds/<name>_<hash>_dds.h`). A stage of
`LangBackend/python.py`'s `run_python`, after `PyGrpcAdapter`.

**Entry point:** `PyDdsAdapter(messages, dest, compliance).Process()` →
`None` (nothing without a `dds` message). Same filter as `DdsAdapter`
(`"DDS" in DdsAdapter._modifiers(msg)`, enums skipped) — imported, not
re-derived.

## Runtimes (copied under `harpia_runtime.dds`)
- `runtime/frame.py` → `.frame`: `Frame(IdlStruct,
  typename="harpia_dds::Frame")`, `@appendable`, `key("message_type")`,
  `payload: sequence[uint8]` — exactly `DdsAdapter/runtime/harpia_dds_frame.idl`.
  mypy sees the payload as `Sequence[int]` (`TYPE_CHECKING` alias: cyclonedds'
  `sequence` isn't generic for mypy); write `bytes`, read back `list[int]`.
- `runtime/transport.py` → `.transport`: `Publisher[M]` / `Subscriber[M]`
  (class attributes `MESSAGE`, `NAME`; ctor `(participant=None,
  topic_name=None)` — own `DomainParticipant` on domain 0 unless given;
  topic defaults to the message name, like C++). `publish(msg) -> bool`
  writes `Frame(NAME, msg.SerializeToString())`; `receive(timeout=0.0)`
  takes ONE sample (WaitSet + ReadCondition for the wait), `None` on
  nothing / unparsable payload (consumed, as C++). `writer_qos()` /
  `reader_qos()` classmethods are the QoS hook (`None` = Cyclone defaults
  in task 1).

## Generated
- `harpia_generated/dds/<name>_<hash>_dds.py` per `dds` message:
  `<name>_publisher(Publisher[<name>])`, `<name>_subscriber(Subscriber[<name>])`.

## Key facts / gotchas
- **Type matching with ddscxx is proven, not assumed** (task 1's "decision
  needed"): cyclonedds-python 0.10.5 expresses `@appendable` + `@key` and
  the generated C++ peer and Python endpoints exchange frames both ways
  (`test_py_dds.py`).
- Cyclone python returns `sequence<octet>` as `list[int]`; `bytes(...)`
  before `ParseFromString`.
- No `matched_*()` counts (the Python API exposes publication/subscription
  matched status only through listeners); tests publish until the first
  sample arrives (discovery), then the sequence.
- Tests use a fresh topic name per test: domain 0 is shared by every
  process on the host.

## Touchpoints
- Depends on: `DdsAdapter._modifiers`, `cyclonedds==0.10.5` (pyproject
  extra `dds`), the `_pb2` modules.
- Tested by: `UnitTests/test_py_dds.py` (C++ peer: `UnitTests/py_dds_interop/`).
