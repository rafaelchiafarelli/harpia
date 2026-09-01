## Fuzz harness — JSON parser (+ the shared fuzz driver)

Scoped 2026-09-01. Task 2 of static-fuzz-ci. Carries the **shared fuzz
driver** that tasks 3 and 4 extend, plus the first target: the JSON
parser. Independent of task 1.

### Decisions (settled during scoping — do not re-litigate)

- **No libFuzzer.** A hand-rolled driver `UnitTests/fuzz/harpia_fuzz_main.cpp`,
  built with `g++ -std=c++17 -O1 -fsanitize=address,undefined
  -fno-sanitize-recover=all` (g++ + ASan/UBSan are already in the image).
- **Driver shape:** `argv` = `<target> <corpus-dir> [iterations] [seed]`.
  For each seed file it calls the target once as-is, then runs a seeded
  xorshift bit-flip / truncate / duplicate mutator for `iterations`
  (default 5000, env `HARPIA_FUZZ_ITERS`) total, seed default 0x9E3779B9
  (env `HARPIA_FUZZ_SEED`). Any sanitizer abort → non-zero exit with the
  offending input hex-dumped and the seed printed for replay. A parser
  returning `false` is **not** a failure — only a crash / sanitizer trip
  is.
- **Targets are compile-time selected** (`-DHARPIA_FUZZ_TARGET=json`) so
  one `.cpp` covers all three; each target is a small
  `bool run(const std::string&)` calling the real entry point on a
  scratch `DynamicMessage` (protobuf reflection — no dependency on a
  specific generated message; `google::protobuf::DynamicMessageFactory`
  over a descriptor from the generated `.proto`, or a fixed vendored
  descriptor — implementer's call, document it).
- **JSON target:** `harpia::serialize::from_json(const std::string&,
  Message*)` (`SerializeAdapter/runtime/harpia_serialize.h:64`).
- **Seed corpus:** `UnitTests/fuzz/corpus/json/` — a handful of checked-in
  files: a valid nested message, an empty object, deeply-nested braces,
  huge-number / long-string / unicode-escape / trailing-garbage cases.
- **Harness: pytest** `UnitTests/test_fuzz_parsers.py`,
  `skipif(shutil.which("g++") is None)`, `@pytest.mark.fuzz`. Compiles the
  driver into `tmp_path`, runs the JSON target against the corpus, asserts
  exit 0. Bounded so it costs seconds.

### Contract

**In:** `g++` with ASan/UBSan (image, present). `harpia_serialize.h` (repo,
present). A protobuf descriptor for a scratch message.

**Required:** nothing from any epic or Foundation. Tasks 3–4 depend on
this task (the driver).

**Delivered:**
- `UnitTests/fuzz/harpia_fuzz_main.cpp` — the driver + the mutator +
  the `json` target, `-DHARPIA_FUZZ_TARGET` switch with `xml`/`soap`
  stubs `#error`-ing until tasks 3/4 fill them.
- `UnitTests/fuzz/corpus/json/*` — the seed corpus.
- `UnitTests/test_fuzz_parsers.py` — the gated, marked pytest job (JSON
  case; a parametrized shell tasks 3/4 slot into).
- `UnitTests/fuzz/README.md` — how to run a longer campaign by hand
  (`HARPIA_FUZZ_ITERS=5000000 ...`) and how to replay a crash from the
  printed seed.

**Pre-work:** the seed corpus files are authored by this task (small,
hand-written — not separate scoping).

**Tests:** the fuzz run *is* the test. Acceptance gate: `HARPIA_FUZZ_ITERS`
at the default, clean exit in Docker, before marking done. A one-off
longer local campaign (≥1e6 iters) is encouraged and its result noted in
the commit, but not required to pass in CI.

**Out of scope:** the XML target (task 3), the SOAP target (task 4), a
persistent/growing corpus, coverage-guided mutation, a nightly job.

---
## Epic context — static-fuzz-ci

See the epic `README.md`. Tasks 3 and 4 are thin additions on this task's
driver; task 1 (cppcheck) is fully independent.
