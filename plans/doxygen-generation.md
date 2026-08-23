# Doxygen Generation: Teaching Consumers to Use the Generated Library, Not Just Decorating It

**Status, updated 2026-08-23: folded into
`plans/medical_devices/schedule/foundation.md` as F6 (one-time plumbing)
plus Ground Rule 6 (an ongoing discipline every future track follows, not
a deferred track of its own).** This file is no longer "scoped, not
started" waiting for its own session — the mechanical setup (§2 below) is
F6, and §3's "comments emitted by the templates" work happens
incrementally, one track at a time, as each track touches its own
consumer-facing templates, per Ground Rule 6. This file now lives on as
the **pitfall table in §4** — a living reference every track adds to when
its own work introduces a consumer-relevant pitfall not already listed,
so the table (and the doc-comments built from it) don't go stale. Read
`foundation.md`'s Ground Rule 6 and F6 contract first; they're the
current source of truth for *when*/*how* this gets built. This file keeps
the *why* (§1) and the *what to watch for* (§4), not duplicated there.

Replaces the narrower framing that used to
live in `plans/medical_devices/schedule/gaps-not-yet-tracked.md` ("Doxygen-
style comment emission ... + a Doxyfile/CMake target" — treated as a pure
documentation-quality/cosmetic gap). That framing undersells the job.

## 1. Who this is actually for

A harpia consumer never sees this repo, `USAGE.md`, or any adapter's
`CLAUDE.md`. All they get is the generated project — headers under
`generated/cpp/...` they `#include` and link against (`USAGE.md` §6). Every
pitfall a consumer can hit today is already known and written down, just in
the wrong place: internal engineering docs meant for people working *on*
harpia, not people working *with* what it outputs. The goal of this work is
to move the consumer-relevant subset of that knowledge into the generated
code itself, as Doxygen comments, so it travels with the artifact instead
of staying locked in this repo.

This also happens to be closer to what was actually asked for originally
(`README.md:337-341`, design-vision spec text): "All code is documented via
doxygen. All interfaces ... must have a usage example." The
gaps-not-yet-tracked framing scoped that down to bare comment emission with
no example/usage obligation; this doc restores the "explain how to use it
and how to not misuse it" intent, short of the full usage-example-run-as-
integration-test claim (see §5, non-goals — that's a bigger, separable
project).

## 2. The mechanical part (still small, still true) — this is now Foundation's F6

- A `Doxyfile` + CMake target (`doxygen` target, `add_custom_target`) to
  build HTML docs from the generated tree. Not novel — standard Doxygen/CMake
  wiring.
- `USE_MDFILE_AS_MAINPAGE` (or `@mainpage`) pointed at a landing page
  assembled from the relevant slice of `USAGE.md` (§4 "What gets
  generated", §6 "Wiring the generated code into your own project", §11
  "Notes & limits") rather than re-authoring that narrative — one place to
  keep it accurate, referenced instead of duplicated per header.

This part alone is what gaps-not-yet-tracked.md scoped, and it's still
correct as far as it goes — it's just not the part that teaches anyone
anything. Comments are the actual deliverable; this is the plumbing that
displays them.

## 3. The actual work: comments emitted by the templates, not hand-written

Every consumer-facing header is *produced* by a `str.format` template
(`loadTemplate`/`_render`, per `util/CLAUDE.md`), not authored by hand — so
Doxygen comments have to be emitted by those templates, with real
per-message/per-field content substituted in, not generic boilerplate
copy-pasted everywhere. Adapters that write consumer-facing headers today
(`write_if_different` callers, per the earlier `grep`): `JsonAdapter`,
`XmlAdapter`, `Database/{SqlAdapter,CrudlAdapter,GrpcServiceAdapter,
DbIoAdapter,RestAdapter,SoapAdapter,WsdlAdapter}`, `ZmqAdapter`,
`protoFile/FileCreator.py`. Each needs its wrapper/DAO template updated to
emit a doc comment block, not just the wrapper it already generates.

## 4. Known pitfalls to surface, and where they land

**This table is now a living reference, per Ground Rule 6 — append to it,
don't just consult it.** When a track's own session adds a
consumer-facing template/adapter behavior a future consumer could get
wrong, add a row here in that same session, then emit the corresponding
doc-comment. The starting set below was pulled from what was already
known and documented internally — the point of this section was "port
it", not "discover it fresh," and that's still true for whatever's
already written down in an adapter's own `CLAUDE.md` as a gotcha a
consumer (not a harpia contributor) could hit:

| Pitfall | Source of truth today | Where it should land |
|---|---|---|
| Never hand-edit generated files — regeneration is write-if-different and silently overwrites/prunes hand edits | `USAGE.md` §11 | `@warning` at the top of every generated header (mainpage: full explanation) |
| `ID_*` primary key is caller-assigned, never DB-auto-generated | `USAGE.md` §11 | DAO `create()` doc comment (`Database/CrudlAdapter.py`) |
| Hidden trailer fields (`ID_`, `STATUS_`, `ERROR_`, `ORIGINATOR`) exist on every message even though the user didn't declare them | `util/CLAUDE.md` `_HIDDEN_PREFIXES`, `message/Variables.py AddHiddenVariables` | Message class doc comment (`protoFile/FileCreator.py`'s templates) |
| XML: a singular **message** field is only emitted when `HasField` is true — an absent child is not the same as an empty-but-present one; getting this backwards can persist a phantom row via the DB adapters | `XmlAdapter/CLAUDE.md` | `to_xml`/`from_xml` doc comment (`XmlAdapter/templates/wrapper.h.tmpl`) |
| `table_name` trailing `;` means private (owner-only) vs public visibility — known per-message at generation time | `README.md:315-320` (spec) | Message/DAO class doc comment, substituted per message |
| `required`/`unique`/`pagination[size]`/`size` field modifiers and what they enforce | `README.md:296-304` (spec) | Per-field setter/accessor doc comment, substituted per field |
| Serializers are contractually crash-free; OOM returns a standardized error, not a crash | `README.md:330-332` (spec) | JSON/XML adapter class-level doc comment |
| Filenames are `<name>_<hash>`-qualified and get pruned/regenerated when the root `.harpia` (or an import) changes | `util/CLAUDE.md` | Top-of-file note (auto-generated banner), not per-header prose |

(See the living-reference note above the table — this was originally
written as a one-time starting set; per Ground Rule 6 it isn't anymore.)

## 5. Non-goals

- **Usage examples run as integration tests**, per the full spec text
  (`README.md:339`). That's a real, larger, separable project — it implies
  generating `@code`/`@example` blocks whose content is exercised by
  something in `TestAdapter`/Stage 14 (`test_stage14.py`'s ctest wiring),
  so the example in the docs is provably not stale. Worth scoping on its
  own once this lands; not required to close this doc.
- **Rewriting `USAGE.md`**. It already carries the narrative content; this
  work references/reuses it (mainpage) and distributes the *specific,
  per-artifact* pitfalls that USAGE.md can't carry because it doesn't know
  a given consumer's actual message/field names.
- **Doxygen-documenting harpia's own Python generator source.** Out of
  scope — this is entirely about the emitted C++ a consumer builds against.

## 6. Verification

- The `doxygen`-gated zero-warnings test (skipped when the `doxygen`
  binary is absent, same pattern as the C++-toolchain-gated tests in
  `tests/CLAUDE.md`) is F6's job — see `foundation.md`'s F6 contract.
  It's what makes Ground Rule 6 mechanically enforceable rather than a
  written convention only: a track that forgets a doc-comment fails this
  test.
- **Per-track job, not F6's:** at least one golden-style snapshot
  assertion (mirroring `test_golden.py`) on that track's own generated
  header's doc-comment block, so the *content* of a pitfall note (e.g.,
  the `HasField` warning) can't silently regress to generic boilerplate
  in a later refactor without the test noticing. Add one alongside
  whatever pitfall-table row (§4) the track's own session adds.
