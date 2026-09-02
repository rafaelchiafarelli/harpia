# harpia fuzz harness (static-fuzz-ci epic)

A single hand-rolled driver, `harpia_fuzz_main.cpp`, fuzzes the three
string-in / message-out parser entry points with no socket in the loop:

| target | entry point | header |
|--------|-------------|--------|
| `json` | `harpia::serialize::detail::from_json` | `serialize/harpia_serialize.h` |
| `xml`  | `harpia::xml::from_xml` *(task 3)* | `xml/harpia_xml.h` |
| `soap` | SOAP envelope parse path *(task 4)* | `soap/…` |

The target is selected at compile time
(`-DHARPIA_FUZZ_TARGET=json|xml|soap`). The scratch message is a fixed
descriptor built in-process (`FuzzMsg`: a scalar of every wire type, a
repeated string, `bytes`, a nested and a repeated-nested sub-message) --
no dependency on any generated `.proto`.

`pytest UnitTests/test_fuzz_parsers.py` builds one sanitizer binary per
target and runs it against `corpus/<target>/` for a bounded, deterministic
budget. A parser returning `false` is a rejected input, not a failure --
only an ASan/UBSan trip (which aborts) fails the run.

## Run a longer campaign by hand

```sh
# generate the C++ tree once
python3 UnitTests/run_pipeline.py /tmp/harpiafuzz

g++ -std=c++17 -O1 -g -fsanitize=address,undefined -fno-sanitize-recover=all \
    -DHARPIA_FUZZ_TARGET=json \
    -I /tmp/harpiafuzz/build/generated/cpp -I third_party/tinyxml2 \
    $(pkg-config --cflags protobuf) \
    UnitTests/fuzz/harpia_fuzz_main.cpp third_party/tinyxml2/tinyxml2.cpp \
    -o /tmp/fuzz_json $(pkg-config --libs protobuf)

# argv: <target> <corpus-dir> [iterations] [seed]
HARPIA_FUZZ_ITERS=5000000 /tmp/fuzz_json json UnitTests/fuzz/corpus/json
```

`HARPIA_FUZZ_ITERS` / `HARPIA_FUZZ_SEED` may also be passed positionally
(`... json <corpus> 5000000 0x1234`).

## Replay a crash

On a sanitizer death the driver hex-dumps the offending input and prints
the line

```
---- replay: HARPIA_FUZZ_SEED=0x9e3779b9  (target=json phase=mutate iter=4211) ----
```

Re-run with that exact `HARPIA_FUZZ_SEED` (and the same
`HARPIA_FUZZ_ITERS`) -- the xorshift stream and the per-seed order are
fully determined by it, so the same `iter` reproduces the same input. The
`phase=seed` case means a checked-in corpus file itself is the trigger
(index = `iter`).

## Corpus

Small, hand-authored seed files, one directory per target. This is a
seed corpus, not a persistent/growing one -- coverage-guided mutation and
a nightly job are explicitly out of scope for this epic.
