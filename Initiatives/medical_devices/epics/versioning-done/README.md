# Versioning / git integration

Planning complete 2026-09-01 — two task files under `tasks/`. This README
is the epic-level context; the per-task contracts live in the task files.

## What this epic is

Git fork-tracking metadata for a generated project — commit, ref,
dirty-tree flag, `git describe`, origin URL, and the fork-point commit —
emitted as fields **within** the process-artifacts epic's existing
`ComplianceReport/`/SBOM output. Not a new registry, not a sidecar file:
"one more field in something it already emits."

## Decided (do not re-litigate)

- **2026-08-23 — folded into `ComplianceReport/`.** The original
  deliverable ("version stamps feeding the registry's associated/calculated
  version fields") targeted the continuable-process work's registry, which
  was never built (crash/interrupt recovery shipped 2026-08-19 via
  `write_if_different`, no registry at all — see `../foundation-handoff.md`).
  The fork-tracking feature itself is still a real unbuilt gap; the open
  question was only *where the stamps live now*. Answer: extend the
  process-artifacts epic's module in place. This epic depends on the
  process-artifacts epic (its `sbom-emission` task), not on the
  continuable-process work.
- **2026-09-01 — collection mechanism: shell out to the `git` binary.**
  Not a hand-rolled `.git/` parser — the fork-point field needs
  `git merge-base`, infeasible without the binary. `git` is added to the
  Docker image (`Dockerfile` `apt-get` list) so the task-2 integration
  tests run in canonical CI; this reverses the `sbom-emission` task's "no
  image change" stance, on purpose.
- **2026-09-01 — graceful absence is a contract.** No git / no repo / a
  failing subcommand → each field is the string `"unknown"`, never
  omitted or fabricated, never a raise. Mirrors `harpia:crypto_backend` →
  `"unknown"`. It has its own test; it is not merely a fallback.
- **2026-09-01 — output shape:** six `harpia:git_*` entries in `bom.json`
  `metadata.properties[]`, after the existing five `harpia:*` pairs. Not
  the CycloneDX `pedigree.commits` structure (too heavy for one field).
- **2026-09-01 — golden determinism:** a monkeypatchable
  `collect_git_state` seam for unit tests + per-key sentinel normalization
  in `run_pipeline.py::_collect_compliancereport`, the same approach
  already used for `metadata.timestamp`.
- **2026-09-01 — one `requirements.py` row** (`applies_to="project"`) for
  build/version provenance as regulatory evidence; `HARPIA_TOOL_VERSION`
  bumps `0.1.0` → `0.2.0`.

## Receives (done before this epic starts)

- **F1** from Foundation — shipped.
- **the process-artifacts epic's `sbom-emission` task** merged (the
  `ComplianceReport/` module must exist to extend) — shipped. Task 2 only;
  task 1 needs nothing from it.

## Gives

- `harpia:git_*` fork-lineage fields inside `bom.json`, recoverable for
  any generated project by reading its `ComplianceReport/` output;
  graceful `"unknown"` everywhere when git is absent.
- **Consumed by:** the process-artifacts epic's output is what a
  regulatory submission reads — these fields become part of that same
  evidence, not a separate consumer. This epic extends that module in
  place.

## Tasks

| # | File | Delivers | Depends on |
|---|---|---|---|
| 1 | `tasks/1-git-fork-tracking-metadata-collection.md` | `Util/gitstate.py::collect_git_state()` + `git` in the Docker image + `test_gitstate.py`. No pipeline/output change. | F1 |
| 2 | `tasks/2-wire-version-lineage-into-compliancereport-output.md` | six `harpia:git_*` props in `bom.json`; golden normalization; one `requirements.py` row; `HARPIA_TOOL_VERSION` → `0.2.0`. Closes the epic. | task 1 merged; `sbom-emission` merged |

## Files this epic touches

- **Task 1:** `Util/gitstate.py` (new), `Dockerfile` (one line),
  `Util/CLAUDE.md`, `UnitTests/test_gitstate.py` (new).
- **Task 2:** `ComplianceReport/ComplianceReport.py`,
  `ComplianceReport/requirements.py`, `UnitTests/run_pipeline.py`
  (`_collect_compliancereport`), `ComplianceReport/CLAUDE.md`,
  `UnitTests/golden/compliancereport/*`, the task-2 test file.

## Watch for

- This epic does **not** touch `main.py` orchestration — the old
  continuable-process-coupled scoping assumed it did.
  `ComplianceReport(...)` is already called at pipeline step 15.
- `git` landing in the image is a one-time rebuild per clone;
  `Docker/run.sh` picks the per-Dockerfile image tag automatically.
