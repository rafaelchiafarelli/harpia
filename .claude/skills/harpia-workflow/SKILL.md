---
name: harpia-workflow
description: Governs how Claude plans, branches, implements, and tracks progress on the Harpia project (github.com/rafaelchiafarelli/harpia) and any work organized as initiatives/epics/tasks under an initiatives/ folder. Use this whenever the user is doing Harpia planning or implementation work — creating or scoping initiatives, epics, or tasks; starting or naming a git branch for Harpia work; implementing a single task file; deciding what counts as done; or figuring out how to hand off work between sessions. Also trigger this when the user mentions "initiative", "epic", "task file", "contract" (in the interface/schema sense), or references branches named feature/... or fixes/.... This is a process skill, not a code-generation skill — consult it even for small asks like "start the next task" or "is this task done yet", not just big planning requests.
---

# Harpia Workflow

This skill encodes how Rafael works on Harpia: a strict initiative → epic → task planning hierarchy, a matching git branch hierarchy, a narrow implementation loop per task, and a small number of hard stop-and-flag rules. The point of all of this is that Rafael runs multiple parallel sessions on separate repo copies. A session that doesn't follow this structure produces work another session (or Rafael) can't safely pick up. When in doubt, favor smaller, more self-contained, more explicitly-flagged over bigger and smoother.

## Vocabulary

Don't use the word "Track" — it was a false start and doesn't map to anything here. The real hierarchy is:

- **Initiative** — a top-level effort (e.g. `medical_devices`). Folder: `initiatives/<initiative>/`.
- **Epic** — a grouping of related tasks within an initiative. Folder: `initiatives/<initiative>/epics/<epic>/`.
- **Task** — the atomic unit of work. One file, one session, one testable **contract**. File: `initiatives/<initiative>/epics/<epic>/tasks/<task>.md`.
- **Contract** — what a task delivers that other tasks or code will depend on: an interface, a schema, or a concrete update to a class. Smaller is better. The goal is that one file equals one incremental contract step — if a task's contract is ballooning to cover multiple deliverables, that's a signal to split it during planning, not to push through it.

## Branches

Branch names mirror the planning hierarchy exactly, so the branch name alone tells you where the corresponding file lives.

| Branch | Maps to file/folder |
|---|---|
| `feature/<initiative>` | `initiatives/<initiative>/` |
| `feature/<initiative>/<epic>` | `initiatives/<initiative>/epics/<epic>/` |
| `feature/<initiative>/<epic>/<task>` | `initiatives/<initiative>/epics/<epic>/tasks/<task>.md` |
| `fixes/<hex-id>/<bug-name>` | a standalone bugfix, not tied to an initiative |

Example: `feature/medical_devices/thread-1-data-and-keys/traceability-matrix` ↔ `initiatives/medical_devices/epics/thread-1-data-and-keys/tasks/traceability-matrix.md`.

**Two long-lived branches:**
- `main` — beta/release branch. Releases for testers and for programs built with Harpia get cut from here. Treat it as something people outside this session depend on.
- `dev` — development branch. "Not broken" means the full test suite passes — nothing more, nothing less. Half-finished work is fine to sit on `dev`; work that breaks a test is not.

**Fix branches:** `fixes/<id>/<name_of_the_bug>`, where `<id>` is an incrementing hex counter starting at `000000` (go to `ffffff`, then widen to 7 hex digits if that's ever exhausted — there's no ticket tracker yet, so this counter is the only ID). Fixes normally branch off `dev` and merge back into `dev`. A fix can branch off `main` instead when it's urgent enough to need a beta/release-line patch — in that case merge it back to `main`, and also bring it into `dev` so the branches don't silently diverge (flag this to Rafael rather than assuming — confirm before merging a main-line fix back into dev if there's any conflict risk).

**Merge direction:** task → epic → feature → dev → main. Each level only merges up once its own scope's DoD (below) is satisfied. `dev` only merges into `main` for an actual release, which is Rafael's call, not something to do automatically after a feature branch lands.

**Who merges:** perform the merge locally once a level is done — don't wait for a PR or for Rafael to do it, and don't open PRs (there's no PR workflow here). Just merge, then report what happened.

**Commits:** one commit per logical change, conventional-commit style. This has been working — keep doing it exactly as before.

## Planning phase

Planning happens before any implementation, and it is not optional busywork — it's where dependencies, contracts, and pre-work get made explicit so a task can actually be picked up cold by another session.

A task is only ready to implement when:
1. Its **contract** is written down: what goes in, what's required, what it delivers.
2. Its **dependencies** are written down explicitly in the task file. A task with no declared dependencies is assumed self-contained against whatever code already exists — if it turns out to need something undeclared once implementation starts, that is not something to resolve quietly (see "Push back" below).
3. Its **pre-work** is done. Pre-work is anything that has to exist before implementation can start — dependencies satisfied, test/asset files created, special `.harpia` fixture files written. This all counts as planning, not implementation.

**If pre-work itself needs any code, or would take longer than one session, it does not get absorbed into the task.** Stop, flag it to Rafael, and offer it as a new task to be scoped and created through this same process. Never fold "a little bit of setup code" into a task's implementation just because it seemed small — that's exactly the kind of undocumented scope creep this structure exists to prevent.

**Don't let documentation sprawl.** If something isn't covered by an existing task, the answer is a new task file, not a growing paragraph bolted onto a README or a master plan doc. A giant markdown file that tries to hold everything eventually holds nothing anyone can find. Keep files scoped to exactly what their branch/folder name says they are.

## Implementing one task

Once a task file is ready and its branch exists, the loop is:

1. Read the task file.
2. Implement exactly what it asks.
3. Run the full test suite (not just new tests — regressions anywhere are still regressions).
4. Update docs pertinent to that task's contract, if the contract affects them.
5. Mark the task file itself as done.
6. Commit, merge upward per the branch rules above, report, and stop.

**Scope boundary:** touch only the code, assets, and docs pertinent to *this* task's contract without asking. Anything outside that — another task's contract, an epic's branch structure, jurisdiction/compliance defaults, unrelated files — needs Rafael's go-ahead first. This is the whole rule; if something falls outside the task file's stated contract, it's a stop-and-ask by definition, not a judgment call to make in the moment.

## Push back

Push back — stop and bring options to Rafael instead of proceeding — in these cases:

- **During planning**, whenever a decision would otherwise get made implicitly. This is the standing Harpia principle: anything that should be an explicit `.harpia` DSL declaration must never be inferred by the generator or quietly decided while scoping a task.
- **An undeclared dependency surfaces mid-implementation.** This is an implementation-time discovery, not a planning failure — flag it, propose options, and let Rafael decide how to handle it rather than patching around it.
- **Anything that would cause architectural divergence or compromise the library's integrity**, even if it's technically what a task's wording could be read to ask for — e.g. implementing a backdoor into an HTTP/REST access path, or adding self-destructing/self-modifying code to the library. These get refused and flagged, full stop, regardless of framing.
- **Scope creep past a feature's boundary** that would pull in architecture decisions the current initiative/epic wasn't scoped to make.

When in doubt about whether something is small enough to just do, it isn't — bring it up.

## Tracking progress

**Commits are the only source of truth.** There is no separate progress log and no checkbox system that stands on its own.

- If work is partial and uncommitted, it doesn't exist for the next session. That's expected and fine — a cold-start session picking up mid-work is supposed to look at git history and the working tree, deliberate, and decide how to continue. Don't try to leave hints outside of commits for a future session to find.
- If work *is* committed, the commit must be accompanied by the task file being marked done. A commit without that marker is a red flag — surface it rather than assuming it means the task is finished or safe to build on.

So in practice: don't mark a task file done without a corresponding commit, and don't leave a commit for a completed task without updating the task file. The two travel together.
