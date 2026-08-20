# Crash/Interrupt Recovery: the CMake/Make Strategy, Not a Registry

Status: scoped and implemented (this doc + `util/util.py`'s atomic writes).
Closes the backlog item in `plans/README.md` and supersedes the
sha256-registry/marker design sketched in `harpia.architecture.md`'s
"continuable process" section.

## 1. The question

`plans/README.md`'s backlog carried: "True crash/interrupt recovery (resume
a killed mid-run generate) -- the sha256-registry/marker half of
`harpia.architecture.md`'s 'continuable process' that the write-if-different
work explicitly did not attempt." The architecture doc's answer to this is
heavyweight: per-stage start/finish markers, a `.sha256` file next to every
output plus a duplicate entry in a registry, and reconciliation logic to
tell which stage a resumed run should pick up from.

That machinery solves a real problem -- but it's the wrong shape for it.
Build systems (`make`, `ninja`, `cmake --build`) solved the identical
problem decades ago without a registry: **a target is either fully built or
it doesn't exist; recovery is "rerun the build," not "resume the exact
interrupted step."** Two mechanisms make that safe and cheap:

1. **Idempotent, content-compared regeneration.** `make`/`ninja` skip a
   target whose inputs haven't changed since it was last built (mtime-based
   dependency graph). Rerunning after a crash is cheap because most targets
   are already up to date.
2. **A target can never be observed half-written.** GNU Make's documented
   behavior: if it's killed while a recipe is running, it deletes the
   target the recipe was updating, specifically "to make sure that it is
   not left in a half-updated state." A build tool never trusts a file at
   its final path unless the step that produced it ran to completion.

Harpia already had (1). It was missing (2).

## 2. What was already true

`Util.util.write_if_different`/`copy_if_different`/`prune_stale_outputs`
(landed for the write-if-different work, `plans/README.md`'s "Done" row)
already give harpia something *stronger* than make's mtime-based check:
every write compares full **content**, not timestamps. Concretely, that
means a killed-and-rerun generate was already closer to safe than the
backlog note assumed:

- If `write_if_different` gets killed mid-write, the file at `path` is left
  truncated -- but with content that doesn't match what the next run
  computes for it. `write_if_different` re-opens, re-reads, sees a
  mismatch, and rewrites. **Self-healing by construction, no marker
  needed** -- the file's own content *is* the marker.
- Rerunning the whole pipeline is the only "resume" operation there is.
  There's no partial-stage state to reconcile, because every stage's output
  is independently content-checked on every run.

So most of the "continuable process" spec text was already satisfied
implicitly, just never written down as the answer.

## 3. The actual gap: writes weren't atomic

`write_if_different` and `copy_if_different` wrote to `path`/`dst` in
place (`open(path, "w")`, `shutil.copy2`). That's not a correctness hole
for the crash-and-rerun case above (content-mismatch self-heals it), but it
breaks the *stronger* guarantee build tools rely on: **anything currently
sitting at the final path is either the complete old file or the complete
new file, full stop** -- no observer, at any point in time, sees a partial
one. Without that:
- A parallel reader (a `cmake`/`make` build kicked off against the output
  tree while a slow regenerate is still running, or simply the next stage
  of the same pipeline run reading a file another adapter just wrote) could
  read a truncated file mid-write and misbehave, not just a killed-and-rerun
  generate.
- It's the one place harpia's behavior didn't actually match the
  make/ninja model this doc is invoking.

## 4. The fix

`util/util.py` now routes every write/copy through `_atomic_replace(dst,
populate)`: `populate` builds the new content into a temp file created in
the *same directory* as `dst` (`tempfile.mkstemp(dir=..., prefix=".{basename}.")`,
required so the final `os.replace` is a same-filesystem rename, not a
cross-device copy), then `os.replace(tmp, dst)` -- atomic on POSIX and
Windows. On any exception (including the populate step failing partway),
the temp file is removed and the exception re-raised; `dst` is never
touched until the rename succeeds.

```python
def _atomic_replace(dst, populate):
    dirpath = os.path.dirname(dst) or "."
    fd, tmp = tempfile.mkstemp(dir=dirpath, prefix=".{}.".format(os.path.basename(dst)))
    os.close(fd)
    try:
        populate(tmp)
        os.replace(tmp, dst)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
```

`write_if_different` and `copy_if_different` both call it; `copy_tree_if_different`
gets it for free since it's built on `copy_if_different`. This is the
entire fix -- no new file format, no registry, no markers.

A real `kill -9` (uncatchable, the `except` block never runs) can still
leave a stray `.{basename}.xxxxxx` temp file behind next to `dst`. That's a
harmless cosmetic leftover, not a correctness issue: the temp prefix starts
with `.`, so it never matches `_NAME_HASH_RE` and `prune_stale_outputs`
leaves it alone; it also never collides with a real output name. Not worth
building cleanup machinery for -- the same residue class `ninja`/`cmake`
leave behind after a hard kill (`.ninja_tmp`, etc.), for the same reason.

Tests: `tests/test_atomic_write.py` simulates the crash by making
`os.replace` raise partway through (deterministic; a real `SIGKILL` race
would be flaky without proving anything `os.replace`'s documented atomicity
doesn't already guarantee), and asserts the destination is left exactly as
it was before the call, with no temp file residue in the success path.

## 5. What this replaces in `harpia.architecture.md`

The "continuable process" section's per-stage start/finish markers, `.sha256`
sidecar files, and dual (per-file + main) registries are no longer the
plan. They were solving integrity-verification and staleness-detection
problems that content-compared writes already solve, at the cost of a
second source of truth (the registry) that could itself drift out of sync
with the files it describes -- exactly the failure mode a crash-recovery
mechanism should not introduce. `harpia.architecture.md` should be updated
to point here instead of describing that machinery as aspirational future
work.

## 6. Non-goals / explicitly out of scope

- **Mid-pipeline checkpointing to skip already-completed stages on
  resume**, the way `ninja` skips up-to-date targets without recomputing
  them. Harpia's stages recompute their in-memory output every run
  regardless (content-diffing happens at write time, not before). If
  regeneration cost ever becomes a problem for large specs, that's a
  performance project layered on top of this (e.g. a per-stage output hash
  checked before doing the work, not just before writing it) -- not a
  correctness gap this doc needs to close.
- **Cleaning up orphaned temp files from a real hard-kill.** See §4 --
  harmless, ignored by `prune_stale_outputs` by construction.
- **Non-file side effects** (network calls, one-time ID generation). Harpia's
  generate step has none; if one is ever added, it would need its own
  idempotency story, not this one.
