# Next session

`README.md`'s "Known gaps" section is the live, authoritative list of
feature/perf gaps. `plans/README.md` is the backlog/scoping-doc index —
open items that used to accumulate in this file now live there instead;
this file stays a short handoff note, not an archive.

## This session: main/dev reconciliation + a real breakage found and fixed

`main` and `dev` had diverged at the git-history level (unrelated commit
hashes after an earlier rewrite) without diverging at the content level —
`dev` was a strict superset of `main`. Reconciled by pointing `main` at
`dev`'s tree via an explicit two-parent merge commit (`git commit-tree`),
not a content-by-content conflict resolution — a plain
`git merge --allow-unrelated-histories` produced ~100 spurious add/add
conflicts that weren't real contradictions.

While verifying the environment on a fresh (WSL2/ext4, case-sensitive)
checkout, found `main.py` genuinely broken:
`Logger`/`Message`/`ProtoFile`/`Util` were renamed lowercase at the
directory level, but the import statements across 33 files were never
updated to match. It went unnoticed because it was last verified on a
case-insensitive filesystem, where the mismatch is invisible. Fixed all 33
files; `setup-env.sh` now runs a case-sensitivity import check on `main.py`
so this can't silently reoccur. Full pytest suite: 39 passed, 42 skipped
(Docker toolchain not available on this host — see `[[env-wsl-docker]]`
memory).

## Reminder for whoever picks this up

`git log --oneline origin/dev..dev` to check nothing's local-only (should
be empty). `main` and `dev` should currently have identical trees — verify
with `git diff main dev --stat` (expect empty) before assuming either one
needs the other's work.

`[[harpia-dev-workflow]]` memory has the test/golden-file workflow;
`[[harpia-project-status]]` memory has the full session-by-session history.
`[[harpia-git-case-insensitive-gotcha]]` matters again for any commit
touching `logger/`, `message/`, `protoFile/`, or `util/` — verify with
`git diff --stat HEAD` after committing, not just `git status`, and prefer
running `setup-env.sh`'s import check on a genuinely case-sensitive
filesystem before trusting a rename like this is complete.
