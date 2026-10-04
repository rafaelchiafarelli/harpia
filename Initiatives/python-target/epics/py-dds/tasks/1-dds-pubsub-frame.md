## DDS pub/sub over the shared `harpia_dds::Frame` topic type

- **Depends on:** `py-foundation` task 1 (`cyclonedds` 0.10.5 in the
  image) and task 2.
- **Contract:**
  - `harpia_runtime/dds/frame.py`: an `IdlStruct` declaring **exactly**
    the C++ type from `DdsAdapter/runtime/harpia_dds_frame.idl`. That is
    typename `harpia_dds::Frame`, `@appendable`, a `@key message_type: str`
    and `payload: sequence[uint8]`, so Python and C++ readers/writers match
    on the same topic.
  - Generated `harpia_generated/dds/<name>_<hash>_dds.py` per `dds` message
    (same filter as `DdsAdapter`):
    - `<name>_publisher(participant=None)`: its `publish(msg)` serializes
      the protobuf and writes a `Frame(message_type=<name>, payload=bytes)`
      to topic `<name>`;
    - `<name>_subscriber`: `receive(timeout)` takes one sample and parses
      it.
- **Decision needed:** whether Python can express the C++ `@appendable`
  extensibility and key annotations with cyclonedds-python 0.10.5's
  `IdlStruct` such that type matching (XTypes assignability) succeeds
  against `ddscxx`. If it can't, stop and flag. Don't fall back to a
  different topic type silently.
- **Out of scope:** QoS (2), security (3), audit (4).
- **Tests:** a Python pub → Python sub round-trip; a CycloneDDS+g++-gated
  C++ publisher → Python subscriber case and the reverse
  (`test_dds_demo.py` build shape). If CycloneDDS is absent, skip like the
  C++ DDS tests.
