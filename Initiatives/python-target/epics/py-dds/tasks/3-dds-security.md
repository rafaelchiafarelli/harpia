## DDS-Security: fail-safe secured participant

- **Depends on:** task 1.
- **Contract:** `harpia_runtime/dds/security.py`:
  - `SecurityFiles` (the six PKI paths + `complete()`) and
    `SecurityRefused`.
  - `secured_participant(domain_id, files, openssl_provider)` builds the
    participant with a Cyclone `<Security>` config (cyclonedds-python takes
    a config XML string / `CYCLONEDDS_URI`, the same Cyclone-native route
    C++ uses).
  - Incomplete files → `SecurityRefused`. **Never a silent plaintext
    participant.**

  The governance/permissions XML and `dds_security_selection.json` are the
  ones `DdsAdapter` already emits (language-neutral). The python backend
  copies them under `harpia_generated/dds/security/` (or references them;
  record which). Provisioning reuses
  `Assets/cmake/dds_security_provision.sh`.
- **Bar:** a secured Python participant and a secured C++ participant
  exchange data on the same domain. An unauthenticated peer of either
  language receives nothing.
- **Tests:** mirroring `test_dds_security.py`: structural (fail-safe
  refusal, files present) plus the gated fork demo with one secured
  C++ peer, one secured Python peer and one plain peer (receives nothing).
