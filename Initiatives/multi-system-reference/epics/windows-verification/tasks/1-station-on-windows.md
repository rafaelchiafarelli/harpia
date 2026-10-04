## `station` on real Windows, reached from real Linux + Android

- **Executed by the Windows session, not the Linux one.**
- **Depends on:** epic `reference-system`; ideally `load-harness` too.
- **Contract:** `station` builds with MSVC 2022 + vcpkg (`vcpkg.json` from
  the program dir plus the generated project's), runs hardened + pooled
  against PostgreSQL on Windows, and is reached across the LAN by `edge` on a
  Linux box and `handheld` on a physical Android device or emulator, using the
  README's deployment steps unchanged. Any README step that turns out wrong
  is fixed in the README as part of this task.
- **Pre-work:** PKI provisioned with `--san <windows-host-ip-or-name>`.
- **Out of scope:** load at hundreds (Rafael's own runs); a short spawn run
  (e.g. 20 + 20) is in scope to prove Windows accepts concurrent mTLS clients.
- **Tests:** manual, recorded in the README's verification section with date,
  versions (MSVC, vcpkg baseline, PostgreSQL) and observed counters, same
  convention as `USAGE.md` §16's Windows notes.
