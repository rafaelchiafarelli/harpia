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
  nothing / unparsable payload (consumed, as C++). `matched_subscribers()` /
  `matched_publishers()` (a matched-status `Listener`, as the C++ methods).
  **QoS (task 2):** `writer_qos()` / `reader_qos()` (reader = writer) from
  the class's `CRITICAL`: `critical_qos(QUEUE_DEPTH)` = `Reliable(10 s)` +
  `KeepAll` + `ResourceLimits(max_samples=128, -1, -1)`, else `latest_qos()`
  = `BestEffort` + `KeepLast(1)`; `Durability` left `Volatile` (C++'s open
  question).

- `runtime/security.py` → `.security` (task 3): `SecurityFiles` (six paths +
  `complete()`), `SecurityRefused`, `security_config_xml(files, provider)`
  (byte-identical to `harpia_dds_security.h`'s), `secured_participant(
  domain_id, files, openssl_provider="default")` — creates
  `cyclonedds.domain.Domain(domain_id, <xml>)` once per domain id (kept
  alive in a module dict) then a participant on it. Incomplete files, or a
  domain id that already exists in the process (e.g. a plain participant
  made first — Cyclone would silently reuse its config), →
  `SecurityRefused`. Never plaintext.

## Generated
- `harpia_generated/dds/<name>_<hash>_dds.py` per `dds` message:
  `<name>_publisher(Publisher[<name>])`, `<name>_subscriber(Subscriber[<name>])`;
  a `critical` message's classes set `CRITICAL = True` + `QUEUE_DEPTH =
  DdsAdapter.QUEUE_DEPTH` (imported, not re-declared).
- `harpia_generated/dds/security/` (task 3): `governance.xml`,
  `permissions.xml`, `dds_security_selection.json`, written by
  `DdsAdapter.write_security_documents` (the C++ adapter's own code; the
  python stages run *before* the C++ ones, so copying was not an option) —
  same bytes as `generated/cpp/dds/security/`. **Decision (logged 36):
  copied, not referenced** — the Python project stays self-contained. Sign
  with `Assets/cmake/dds_security_provision.sh`. `PyDdsAdapter` takes
  `crypto_backend` (from `ctx`) for the selection record.

## Key facts / gotchas
- **Type matching with ddscxx is proven, not assumed** (task 1's "decision
  needed"): cyclonedds-python 0.10.5 expresses `@appendable` + `@key` and
  the generated C++ peer and Python endpoints exchange frames both ways
  (`test_py_dds.py`).
- Cyclone python returns `sequence<octet>` as `list[int]`; `bytes(...)`
  before `ParseFromString`.
- Matched counts come from listeners (cyclonedds-python has no direct
  matched-status getter); its `Listener` ctor is untyped (one scoped
  `type: ignore[no-untyped-call]`).
- A Python writer of an appendable type writes XCDR2 (`DataRepresentation`
  default); ddscxx reads it -- interop is tested, both profiles.
- Tests use a fresh topic name per test: domain 0 is shared by every
  process on the host.

## Touchpoints
- Depends on: `DdsAdapter._modifiers`, `cyclonedds==0.10.5` (pyproject
  extra `dds`), the `_pb2` modules.
- Tested by: `UnitTests/test_py_dds.py`, `test_py_dds_security.py` (C++
  peer: `UnitTests/py_dds_interop/`, `xml` / secured modes, domain from
  `$HARPIA_DDS_DOMAIN`).
