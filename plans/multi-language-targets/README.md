# Multi-language generation targets (Node/Rust/Python/Java)

**Restructured 2026-08-23** from two standalone files —
`plans/multi-language-targets.md` (written 2026-08-11, the general
methodology + Python recommendation) and `plans/java-target.md` (written
2026-08-22, the addendum that picked Java instead) — into this folder,
using the same thread/track/session pattern built for
`plans/medical_devices/schedule/`. Both original files are deleted; this
folder is the canonical source. `harpia_medical_master_plan.md`'s Track J
(medical_devices' compliance plan) now points here rather than
duplicating the session breakdown — see
`plans/medical_devices/schedule/thread-4-platform-infra/track-j-java-target.md`'s
own thin pointer.

- [thread-1-java-target/](thread-1-java-target/README.md) — Java as the
  first target language (picked over Python for a concrete reason, see
  below). 27 sessions (one deliverable + tests each) in
  [track-j-java-target.md](thread-1-java-target/track-j-java-target.md).

---

## 1. The question this answers

Framed as a choice: **one session per language**, or **one session to
build a generalized "any language" framework** (new target = new template
set + new compiler invocation, no core changes)?

**Answer: neither, cleanly.** A real generalized framework is not
reachable from a single C++ data point — see §2. Adding language #1 is a
multi-session effort in its own right, not a quick session, because
several of harpia's stages don't just need a new template — they need a
different *runtime library* with a different API shape. The realistic
path: **scope and build one language fully, on its own, across several
sessions; extract a shared IR/emission seam only after that language's
concrete shape exists to compare against C++'s** (exactly how
`Database/backends/` wasn't designed until Postgres was a real second
case).

## 2. Per-stage cost methodology

Both language-specific docs that fed this folder used the same table
shape: for each pipeline stage, is retargeting to a new language free
(inherent to the language-agnostic IR), near-free (thin wrapper over a
library the target language already ships), or genuinely new
per-language work? Stages 0–6 (front-end) and `.proto` emission are
**always free** — nothing there is C++-specific, every future target
reuses them untouched. JSON is **usually near-free** — most protobuf
language bindings ship the same well-known JSON mapping built in. DB,
HTTP framework, XML runtime, generated tests, and packaging are
**genuinely per-language work**, because those stages depend on a
runtime library that doesn't exist outside the target language. See
`thread-1-java-target/README.md` §2 for the Java-specific table, built
fresh from the real adapter code rather than extrapolated from any
other language's table (that extrapolation was considered and rejected —
see §3 below).

## 3. Why not build the abstraction first

The Postgres-backend effort only trusted the `DbBackend` interface once
Postgres gave it a second, concrete, already-understood dialect to diff
against SQLite. Guessing the right "any-language back end" interface from
ONE data point (C++) risks baking in C++-shaped assumptions (e.g. "emit a
header file," "template returns raw source text via `str.format`," "no
package manager") that another language's actual shape might not fit at
all. Build one real second language first; the abstraction — if one is
still worth it after seeing two concrete cases — gets extracted the same
way `Database/backends/` was: after, in its own reviewed slice, not
before. This also means a two-language seam (even once Java is real)
stays provisional until a third data point (Python) exists too — see
`thread-1-java-target/README.md` §3.

## 4. Language selection history

1. **2026-08-11 (original `multi-language-targets.md`):** per-stage cost
   analysis recommended **Python** as language #2 *in the abstract* — no
   vendoring/build-toolchain story to invent (`pip install` covers
   everything), `sqlite3` is stdlib, mature boring library choices exist
   for every stage. Rust/Node/Java were explicitly left unscoped —
   extrapolating Python's cost analysis to them by analogy was considered
   and rejected (Python-specific facts like its reflection API shape and
   protobuf JSON support don't transfer to a language with a different
   type system or no runtime reflection).
2. **2026-08-22 (`java-target.md`'s addendum):** a concrete business
   reason overrode the abstract recommendation — an existing fleet of
   Android devices/apps wants harpia-generated Java code **now**, not
   after a Python target lands. This is *not* a re-litigation of "which
   language is cheapest to port in the abstract" — it says nothing about
   which language someone actually needs now. `java-target.md` re-derived
   its own per-stage table from the real adapter code rather than
   extrapolating from the Python table (the same discipline the Python
   doc itself warned against skipping for a third language).
3. **Current: Java is the second target, Python is still third, not
   dropped.** Rust/Node remain unscoped until a second real data point
   (Java) and Python both exist to compare against — item 1's caution
   about extrapolation applies just as much to Java→Rust/Node as it did
   to Python→Rust/Node/Java originally.

## 5. Selector mechanism

Thread a `HARPIA_GEN_LANG` env var (default `cpp`) through `main.py`,
resolved once — same shape as `HARPIA_DB_BACKEND` → `get_backend()`
(`main.py:147-149`, `Database/backends/__init__.py`). Each adapter call
in `main.py`'s orchestration becomes conditional on the target, or, once
a second language's real shape is visible, a `get_lang_backend()`
registry mirroring `Database/backends/__init__.py`'s pattern (see §3 on
why that's not designed yet).

## 6. Scale check

For comparison: a single focused `Database/` seam addition with a known,
narrow shape was 4 commits, ~450 lines, one afternoon. A full language
target touches the equivalent of *every module in the repo* (front-end
reuse aside), each needing its own new library integration, its own test
suite, its own golden-file-equivalent verification story — comparable to
(or larger than) the whole Postgres-backend effort (an 8-slice branch
plan). Java's estimate skews slightly larger than Python's would have,
for two additional reasons specific to Java — see
`thread-1-java-target/README.md` §8.
