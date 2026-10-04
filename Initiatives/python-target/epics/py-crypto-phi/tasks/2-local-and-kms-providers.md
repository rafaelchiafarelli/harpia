## `LocalKeyProvider` (C++-compatible store) + KMS seam + `MockKms`

- **Depends on:** task 1.
- **Contract:**
  - `harpia_runtime/crypto/key_provider_local.py`: a port of
    `harpia_key_provider_local.h`.
    - KEKs persist to `storage_path` in the **same file format** C++
      writes (one `<version> <hex>` line per KEK, truncate-rewrite).
    - Shred appends `<kek_version> <hex>` to `<storage_path>.shred`
      (append-only, never rewrites the KEK store).
    - The fail-safe gate raises `LocalKeyProviderRefused` when
      `phi_at_scale and not acknowledged`; opt in via
      `local_key_provider_acknowledged()` (`HARPIA_ACK_LOCAL_KEY_PROVIDER`)
      or the config field.
  - `harpia_runtime/crypto/key_provider_kms.py`:
    - `KmsClient`, the four-op seam over opaque bytes + int version.
    - `KmsKeyProvider`, which routes every op to the seam and keeps
      per-DEK shred as a local set.
    - `MockKms`, in-memory XOR.
- **Bar:** a store written by the C++ `LocalKeyProvider` loads in Python
  and unwraps the same DEKs, and vice versa. A DEK shredded by one
  language is refused by the other.
- **Out of scope:** a real KMS/HSM binding (same as C++).
- **Tests:**
  - Unit tests mirroring `test_local_key_provider.py` and
    `test_kms_key_provider.py` (restart survival, gate refuses/accepts,
    shred sidecar, swapping providers needs no interface change).
  - A g++-gated cross-language test: C++ writes a store and wraps a DEK;
    Python unwraps it and shreds it; C++ then refuses it.
