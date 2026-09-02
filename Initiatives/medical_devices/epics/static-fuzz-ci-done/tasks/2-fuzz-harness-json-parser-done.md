## Fuzz harness — JSON parser (+ the shared fuzz driver)

Scoped 2026-09-01. **Implemented 2026-09-01.** Task 2 of static-fuzz-ci.
Carries the **shared fuzz driver** that tasks 3 and 4 extend, plus the
first target: the JSON parser. Independent of task 1.

### Decisions (as implemented)

- **No libFuzzer.** Hand-rolled driver
  `UnitTests/fuzz/harpia_fuzz_main.cpp`, built with
  `g++ -std=c++17 -O1 -g -fsanitize=address,undefined
  -fno-sanitize-recover=all` (g++ + ASan/UBSan are in the image).
- **Driver shape:** `argv` = `<target> <corpus-dir> [iterations] [seed]`.
  `<target>` is asserted against the compiled-in target (guards a stale
  binary). For each seed file the target is called once as-is, then a
  seeded xorshift64\* mutator (bit flip / byte set / truncate /
  duplicate-slice / byte insert / byte swap, 1–6 rounds, growth capped at
  64 KiB) runs for `iterations` total calls. Default 5000
  (env `HARPIA_FUZZ_ITERS`), seed default `0x9E3779B9`
  (env `HARPIA_FUZZ_SEED`); both also accepted positionally. A parser
  returning `false` is **not** a failure — only a sanitizer trip is, and
  the sanitizer aborts the process (non-zero exit → the pytest job fails).
  On a sanitizer death a `__asan_set_death_callback` hook hex-dumps the
  current input and prints the seed / phase / iter for replay.
- **Targets are compile-time selected** (`-DHARPIA_FUZZ_TARGET=json`).
  One `.cpp` covers all three; the `xml` / `soap` branches `#error` until
  tasks 3 / 4 fill them.
- **Scratch message = a fixed in-process descriptor.** The driver builds a
  `FileDescriptorProto` (`FuzzMsg`: `string / int32 / int64 / double /
  bool / uint64` scalars, a `repeated string`, `bytes`, a nested
  `FuzzInner`, and a `repeated FuzzInner`) into a private `DescriptorPool`
  and uses `DynamicMessageFactory`. **No dependency on any generated
  `.proto` / `.pb.cc`** — only libprotobuf + the parser's runtime header.
- **JSON target:** `harpia::serialize::detail::from_json(const std::string&,
  Message*)` — the JSON leg of `harpia::serialize::from_string`
  (`SerializeAdapter/runtime/harpia_serialize.h`), which is
  `JsonStringToMessage` with `ignore_unknown_fields`.
- **Seed corpus:** `UnitTests/fuzz/corpus/json/` — 8 checked-in files:
  valid nested message, empty object, deep nesting, huge/overflowing
  numbers, long strings, unicode + bad escapes, trailing garbage, wrong
  types per field.
- **Harness: pytest** `UnitTests/test_fuzz_parsers.py`,
  `skipif` when `g++` / `pkg-config` absent, `@pytest.mark.fuzz`
  (registered in `pytest.ini`; runs by default, `-m "not fuzz"` skips).
  Compiles the driver into `tmp_path` against the `run_pipeline.py` tree,
  runs the JSON target against the corpus, asserts exit 0 and an `ok:`
  line. Parametrized over `TARGETS` — tasks 3/4 append one entry each.

### Contract

**In:** `g++` with ASan/UBSan (image). `harpia_serialize.h` (repo). A
protobuf descriptor for a scratch message — built in-process, no external
input.

**Required:** nothing from any epic or Foundation. Tasks 3–4 depend on
this task (the driver + the pytest shell).

**Delivered:**
- `UnitTests/fuzz/harpia_fuzz_main.cpp` — driver + mutator + `json`
  target; `-DHARPIA_FUZZ_TARGET` switch with `xml` / `soap` `#error`
  stubs.
- `UnitTests/fuzz/corpus/json/*` — the 8-file seed corpus.
- `UnitTests/test_fuzz_parsers.py` — the gated, `fuzz`-marked, parametrized
  pytest job (JSON case active).
- `UnitTests/fuzz/README.md` — how to run a longer campaign by hand and
  how to replay a crash from the printed seed.
- `pytest.ini` — the `fuzz` marker registered.

**Pre-work:** the seed corpus files, hand-authored by this task.

**Tests:** the fuzz run *is* the test. Acceptance gate — met: default
`HARPIA_FUZZ_ITERS` clean exit in Docker (`1 passed in ~3s`), full suite
green. One-off longer campaign run: **2×2 000 000 mutations** (seeds
`0x9E3779B9` and `0xC0FFEE`), ~36 s each, no sanitizer trip.

**Out of scope:** the XML target (task 3), the SOAP target (task 4), a
persistent/growing corpus, coverage-guided mutation, a nightly job.

### Implementation notes

- The task file names the JSON entry point `harpia::serialize::from_json`;
  the actual symbol is `harpia::serialize::detail::from_json` (line 64 is
  inside `namespace detail`). `from_string(in, msg, Format::JSON)` is
  exactly a call to it with no extra logic — the driver calls
  `detail::from_json` directly to fuzz the JSON parse in isolation.
- `ASAN_OPTIONS=detect_leaks=0` for the run: protobuf's `DescriptorPool` /
  `DynamicMessageFactory` internal caches are process-lifetime and LSan
  flags them at exit; not a defect. UBSan runs with `halt_on_error=1`.

---
## Epic context — static-fuzz-ci

See the epic `README.md`. Tasks 3 and 4 are thin additions on this task's
driver; task 1 (cppcheck) is fully independent.
