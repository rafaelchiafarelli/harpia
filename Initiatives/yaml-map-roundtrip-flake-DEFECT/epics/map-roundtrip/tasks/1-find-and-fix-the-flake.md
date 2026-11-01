## Find why the nested map round trip fails intermittently, and fix it

- **Depends on:** nothing.
- **Contract:** `test_yaml_map_negative_int_keys` passes on every run, and it
  still fails if `from_yaml` really loses or changes a map entry.
- **1. Corroborate (red first):** reproduce with a loop (each run about 5 s):

  ```sh
  Docker/run.sh bash -c 'for i in $(seq 1 20); do pytest -q -p no:cacheprovider \
    UnitTests/test_stage10_yaml.py::test_yaml_map_negative_int_keys 2>&1 | tail -1; done'
  ```

  It should fail several times in 20 (about 1 in 3 so far).
- **2. Decide the cause:** on a failing run, print `a` and `b` with
  `DebugString()` or compare them with `MessageDifferencer::Equals`, which
  ignores map order.
  - Equal → test bug: replace the byte comparison at line 294 with a
    semantic one.
  - Different → product bug in `harpia_yaml.h`: fix it there, and check the
    Python YAML reader (`PySerialization/`), which mirrors it. Stop and flag
    this to Rafael first if the fix changes generated output.
- **3. Unit tests (kept):** the same test, then 20 clean runs in the loop above.
  Check the other `SerializeAsString()` comparisons in that file (lines 153,
  180, 204): any that holds a map has the same weakness.
- **Golden move:** none expected for a test fix.
- **Docs:** `UnitTests/CLAUDE.md`, plus `YamlAdapter/CLAUDE.md` if the product
  changes.
