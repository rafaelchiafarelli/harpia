# Multi-language generation targets (Node/Rust/Python/Java)

> Scoping doc, not a build plan. Written 2026-08-11 after discussing README's
> "Beyond the pipeline" gap #5 ("C++ is the only generation target"). Companion:
> [postgres-migration.md](postgres-migration.md) — the `DbBackend` seam that
> abstraction extracted is the closest precedent in this codebase for "one
> concern, N interchangeable implementations," and its lesson (don't design the
> seam until you have 2 concrete cases to compare) directly informs the
> recommendation below.

## 1. The question this answers

Framed as a choice: **one session per language**, or **one session to build a
generalized "any language" framework** (new target = new template set + new
compiler invocation, no core changes)?

**Answer: neither, cleanly.** A real generalized framework is not reachable
from a single C++ data point — see §2. But "one session per language" also
undersells the first one: adding language #1 (recommend Python, see §4) is a
multi-session effort in its own right, not a quick session, because several
of harpia's stages don't just need a new template — they need a different
*runtime library* with a different API shape. The realistic path is: **scope
and build Python fully, on its own, across several sessions; extract a
shared IR/emission seam only after Python's concrete shape exists to compare
against C++'s** (exactly how `Database/backends/` wasn't designed until
Postgres was a real second case — see `postgres-migration.md` §"Route B").

## 2. Per-stage: what's already language-agnostic vs. what's genuinely per-language

| Stage | What it emits today (C++) | Cost to retarget | Why |
|---|---|---|---|
| 0–6 (front-end: `LexicalAnalizer/`, `Message/`) | Tokens → `Message` IR | **Free** | Already fully language-agnostic; nothing here mentions C++. Every future target reuses this untouched. |
| 6/7 `.proto` emission + `protoc` (`ProtoFile/FileCreator.py`, `ProtoCompiler.py`) | `.proto` files, then `protoc --cpp_out` | **Near-free** | `.proto` text is already language-agnostic (`FileCreator.py` has zero C++-specific logic). Only `ProtoCompiler.Process()`'s `protoc --cpp_out` invocation is C++-specific — swap the `--cpp_out` flag for `--python_out`/`--java_out`/etc. (or the appropriate plugin for Rust/Node, see §4). This is the strongest argument that a shared front half is realistic, not aspirational. |
| 13 gRPC stubs (`ProtoFile/GrpcCompiler.py`, `Database/GrpcServiceAdapter.py`) | `.proto` service → `protoc --grpc_out` stub, then a hand-templated impl wired to the DAO | **Split** | The *stub generation* is near-free the same way (protoc has first-party gRPC plugins for Python/Node/Java/Rust). The *impl* (`GrpcServiceAdapter.py`'s template wiring RPCs to the DAO) is a new per-language template, but a fairly mechanical one once the DAO exists. |
| 9 JSON (`JsonAdapter/`) | Thin wrapper over `google::protobuf::util`'s C++ JSON support | **Often free-ish** | Most protobuf language bindings ship the *same* well-known JSON mapping built in (`google.protobuf.json_format` in Python, `protobuf.util.JsonFormat` in Java/JS). The "adapter" may collapse to near-nothing for some languages — genuinely cheaper than C++, not just portable. |
| 10 XML (`XmlAdapter/`) | Hand-written reflection-walking runtime (`runtime/harpia_xml.h`) over `tinyxml2`, since protobuf has no built-in XML | **Real, but bounded** | No language's protobuf binding has built-in XML either, so every target needs an equivalent reflection-walking runtime (Python's `google.protobuf.descriptor`/reflection API is comparable in shape to what C++ does here; other languages vary). This is genuinely new code, but it's ONE runtime file, not per-message templates — same shape as today. |
| 8 DB/CRUDL/migration (`Database/`) | SOCI-backed SQL (`Database/backends/` dialect seam + `CrudlAdapter`/`MigrationAdapter` templates) | **Real, largest piece** | SOCI doesn't exist outside C++. Every language needs its own DB driver with a different bind/extract API (Python: stdlib `sqlite3` + `psycopg2`/`asyncpg`; the CRUDL/migration *logic* — column shape, FK/map/repeated child-table design, the rename/drop/retype migration algorithm — is exactly what `Database/model.py`'s `analyze()`/`map_fields()`/`repeated_fields()` already IS the language-agnostic IR for. This is the best-understood porting target in the whole pipeline precisely because this session + the last two spent real effort making it a clean IR. |
| 11/12 SOAP/REST (`Database/SoapAdapter.py`/`RestAdapter.py`, vendored Crow) | Crow (C++ header-only HTTP) + tinyxml2 | **Real** | Different HTTP framework per language (Python: FastAPI/Flask; Node: Express; Java: Spring; Rust: Axum/Actix), each with different routing/middleware idioms. Credential gate logic (`X-User`/`X-Pswd` check — see `Database/CLAUDE.md`'s gotchas) is simple enough to reimplement per-language without much risk. |
| 13 ZMQ (`ZmqAdapter/`) | cppzmq | **Real, but small** | Every target language has a mature ZMQ binding (pyzmq, zeromq.js, jeromq, `zmq` crate) with a similar socket-pattern API (PUSH/PULL/PUB/SUB) — mechanically similar shape, different syntax. The origin-id scheme (`_origin_id`, `runtime_origin_id()`) is a portable algorithm, not a C++ trick. |
| 14 generated tests (`TestAdapter/`) | CTest + hand-rolled C++ assertions | **Real** | Needs a per-language test runner (pytest, jest, cargo test, JUnit) and translating each `_db_body`/`_json_body`/etc. builder's C++ string templates into that language's syntax. Mechanical per-builder, but there are ~8 of them. |
| Build/packaging (`Assets/`, `third_party/`, generated `CMakeLists.txt`) | CMake + vendored C++ libs | **Real, different shape entirely** | Not a "port" so much as a new problem per language: Python → wheels/`pyproject.toml` + `pip`-installable deps (no vendoring needed — `pip install grpcio protobuf`); Node → `package.json`; Rust → `Cargo.toml` (vendoring-averse ecosystems, unlike C++). `run_harpia.sh`'s "self-contained portable output folder" promise needs a per-language equivalent of "here's how you build this," not a literal CMake translation. |

**Bottom line:** roughly half the pipeline (front-end, proto, gRPC stubs,
often JSON) is at-or-near zero marginal cost per new language — that's a real
result, not hand-waving, and it's *because* the IR already fully separates
"what a message contains" from "how C++ renders it." The other half (DB,
HTTP framework, XML runtime, tests, packaging) is genuine per-language work
with no meaningful shortcut, because those stages fundamentally depend on a
runtime library that doesn't exist outside C++.

## 3. Why not build the abstraction first

`postgres-migration.md` only trusted the `DbBackend` interface once Postgres
gave it a second, concrete, *already-understood* dialect to diff against
SQLite (§3 of that doc is a literal side-by-side table). Guessing the right
"any-language back end" interface from ONE data point (C++) risks baking in
C++-shaped assumptions (e.g. "emit a header file," "template returns raw
source text via `str.format`," "no package manager") that Python's actual
shape might not fit at all (Python has no header/impl split; templates would
more naturally emit importable modules; dependencies are declared, not
vendored). Build Python for real first; the abstraction — if one is still
worth it after seeing two concrete cases — gets extracted the same way
`Database/backends/` was: after, in its own reviewed slice, not before.

## 4. If Python is the pick: why, and what it looks like concretely

**Why Python over Node/Rust/Java for the first port:**
- No vendoring/build-toolchain story to invent — `pip install` covers
  `protobuf`, `grpcio`, JSON (stdlib), and a DB driver. Contrast Rust (needs a
  vendoring-or-crates.io decision harpia hasn't had to make before) or Node/Java
  (different but comparably new packaging stories).
- `sqlite3` is stdlib — the SQLite CRUDL path needs no new dependency at all,
  mirroring today's "vendored SQLite, zero external server" default story.
- Mature, boring choices exist for every remaining stage (FastAPI for REST/SOAP,
  `pyzmq`, `pytest`) — low risk of getting stuck evaluating libraries instead of
  porting logic.
- Front-end/IR work (§2's "free" rows) is the majority of the *codebase*, even
  though it's the minority of the *effort* — Python validates that reuse story
  fastest since there's nothing to build there, only to point `protoc` at.

**Concrete stage-by-stage sketch (not a committed plan):**

| Stage | New module (mirrors existing C++ one) | Library |
|---|---|---|
| 7 | `ProtoCompiler`'s `protoc` invocation gains a `--python_out` path (or a `target_lang` parameter) | `protoc` (already required) |
| 13 (stubs) | Same compiler, `--grpc_out` w/ the Python grpc plugin | `grpcio-tools` |
| 9 | `JsonAdapter` → likely near-pass-through to `google.protobuf.json_format` | `protobuf` (already required) |
| 10 | New `XmlAdapter`-equivalent: a reflection-walking module over `message.DESCRIPTOR` | stdlib `xml.etree` or `lxml` |
| 8 | New `Database/backends`-shaped Python package: same `analyze()`/`map_fields()`/`repeated_fields()` IR, consumed by a new CRUDL-emitting adapter | stdlib `sqlite3`, `psycopg2`/`asyncpg` for Postgres |
| 11/12 | New REST/SOAP adapter emitting FastAPI route modules | `fastapi` (or `flask` if a lighter dep is preferred) |
| 13 (zmq) | New `ZmqAdapter`-equivalent | `pyzmq` |
| 14 | New `TestAdapter`-equivalent emitting `pytest` files | `pytest` (already the harpia dev dependency) |
| packaging | New `Assets`-equivalent: `pyproject.toml` template + a generated `requirements.txt`, no CMake/vendoring | `pip`/`setuptools` or `uv` |

**Selection mechanism:** thread a `HARPIA_GEN_LANG` env var (default `cpp`)
through `main.py`, resolved once — same shape as `HARPIA_DB_BACKEND` →
`get_backend()` at `main.py:147-149` today. Each adapter call in `main.py`'s
orchestration becomes conditional on the target (or, if the eventual
abstraction is worth it once Python exists, a `get_lang_backend()` registry
mirroring `Database/backends/__init__.py`).

## 5. Scale check — this is NOT a quick-session item

For comparison: this session's type-change-migration work — one focused
`Database/` seam addition with a known, narrow shape — was 4 commits, ~450
lines, one afternoon. A full Python target touches the equivalent of *every
module in the repo* (front-end reuse aside), each needing its own new
library integration, its own test suite, its own golden-file-equivalent
verification story. Realistic sizing: comparable to (or larger than) the
whole Postgres-backend effort (`postgres-migration.md`'s 8-slice branch
plan), because Postgres only had to swap a SQL dialect behind an interface
that already assumed "C++, SOCI, header-only" — a Python target can't assume
any of those three.

## 6. Recommendation

1. **Don't build a language-abstraction framework yet.** One data point
   (C++) isn't enough to design it correctly, and a wrong-shaped abstraction
   is worse than none — this codebase's own precedent (`DbBackend`, see §3)
   is to extract seams *after* a second concrete case exists, not
   speculatively.
2. **Pick Python as the second target**, for the reasons in §4.
3. **Scope it as its own multi-session epic**, sliced the way
   `postgres-migration.md` sliced Postgres (§8 there): each slice lands
   independently, leaves the C++ path untouched and green, and is verified
   against its own equivalent of a golden-file suite before the next slice
   starts. A first-pass slice order, mirroring the dependency order already
   implicit in §2's table:
   1. `protoc --python_out` + `--grpc_out` wiring (near-free, proves the
      selector mechanism end-to-end with visible output fastest).
   2. JSON pass-through.
   3. DB/CRUDL/migration (the biggest slice — reuses `Database/model.py`'s
      IR directly, SQLite-only first, Postgres later).
   4. REST/SOAP (FastAPI).
   5. XML runtime.
   6. ZMQ.
   7. Generated tests (`pytest`) + packaging (`pyproject.toml`) + docs.
4. **Only after Python is real**, revisit whether a `Database/backends`-style
   `LangBackend` seam is worth extracting — and let Python vs. C++'s actual
   diffs (not speculation) drive its shape.
5. Node/Rust/Java stay explicitly out of scope until Python validates the
   approach and the effort-per-language number is a measured fact instead of
   a guess.

---

## 7. Addendum (2026-08-18) — cross-referenced from the medical-device plan

`plans/medical_devices/`'s Track J (session-4, and the master plan) picked
Python back up as its "first target language" deliverable — pointed here
rather than re-deriving the choice; read this doc's §2/§4 before touching
that track.

While scoping that plan, the question in item 5 above got asked again
directly — "since we're already committing to a large multi-session
effort, why not extrapolate this doc's Python analysis to Rust/Node/Java
now too?" — and was re-affirmed as still the wrong move, for the same
reason as item 1, made concrete: this doc's per-stage cost table (§2)
leans on Python-specific facts (its protobuf JSON support shape, its
descriptor/reflection API, its DB/HTTP ecosystem) that don't transfer by
analogy to a language with a different type system or no runtime
reflection (Rust has neither the reflection XML needs nor Python's GC;
Node's async-everything model reshapes the DAO/CRUDL layer structurally,
not just syntactically). Writing those languages' costs down anyway would
produce a table that *looks* as authoritative as this one while actually
being unverified guesses — worse than leaving them unscoped, especially
for a plan whose other half depends on auditable, provable claims. Item 5
stands: unscoped until Python is real and a genuine second data point
exists to compare against.

## 8. Addendum (2026-08-22) — Java picked as the actual second target, ahead of Python

Item 5 held until a concrete business reason overrode it: an existing fleet
of Android devices/apps that want to consume harpia-generated Java code
today, not after a Python target lands. This is **not** a re-litigation of
§4's "why Python over Java" reasoning — that reasoning is about which
language is cheapest to port *in the abstract*; it says nothing about which
language someone actually needs *now*. See
[java-target.md](java-target.md), scoped with the same per-stage-table
discipline this doc used (re-grounded in the real adapter code, not
extrapolated from this doc's Python row by analogy — the thing §7 above
warned not to do for Rust/Node applies just as much to Java, so
`java-target.md` re-derives its own table rather than reusing this one's).
Python is still next after Java, not dropped — §5 item 5's reasoning for
deferring a *third* language stands unchanged.
