"""Assembles the Doxygen mainpage for a generated project (Foundation F6).

Per the F6 deliverable: `USE_MDFILE_AS_MAINPAGE` should point at "a landing
page assembled from the relevant slice of USAGE.md (S5 'What gets
generated', S7 'Consuming the generated code from your own app', S16
'Notes & limits') ... referenced, not re-authored, so there's one place to
keep the narrative accurate." Rather than a hand-copied static file that
could drift from USAGE.md, this module extracts those sections' real text
at generation time, every run -- if USAGE.md's S5/S7/S16 change, the next
run's mainpage changes with them, with nothing to remember to update by
hand. (The section numbers were 4/6/11 before the V1 USAGE.md rewrite.)
"""
import os

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: Default location of harpia's own USAGE.md, relative to this repo.
DEFAULT_USAGE_MD = os.path.join(_REPO_ROOT, "USAGE.md")

#: Filename the assembled mainpage is written under in a generated project;
#: must match Assets/Doxyfile's USE_MDFILE_AS_MAINPAGE/INPUT entries.
MAINPAGE_FILENAME = "USAGE_EXCERPT.md"

#: USAGE.md section numbers F6 pulls, in this order: "What gets generated",
#: "Consuming the generated code from your own app", "Notes & limits".
DEFAULT_SECTIONS = (5, 7, 16)


def _extract_section(text, number):
    """Return one `## N. Title` section's full text (heading + body), up to
    (not including) the next top-level `## ` heading, or end of file."""
    lines = text.splitlines(keepends=True)
    heading_prefix = "## {}.".format(number)
    start = None
    for i, line in enumerate(lines):
        if line.startswith(heading_prefix):
            start = i
            break
    if start is None:
        raise ValueError(
            "USAGE.md has no {!r} section heading".format(heading_prefix))

    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("## "):
            end = j
            break

    return "".join(lines[start:end]).rstrip("\n") + "\n"


def extract_usage_sections(usage_md_path=None, sections=DEFAULT_SECTIONS):
    """Assemble the mainpage body: the given USAGE.md section numbers,
    verbatim and in order, prefixed with a title line."""
    path = usage_md_path or DEFAULT_USAGE_MD
    with open(path, "r") as f:
        text = f.read()
    parts = [_extract_section(text, n) for n in sections]
    return "# Harpia-generated project\n\n" + "\n\n".join(parts)


def write_mainpage(dest, usage_md_path=None, sections=DEFAULT_SECTIONS):
    """Write the assembled mainpage to `<dest>/USAGE_EXCERPT.md`
    (write-if-different, same convention as every other generated
    artifact). Returns the written path."""
    from Util.util import write_if_different

    content = extract_usage_sections(usage_md_path, sections)
    path = os.path.join(dest, MAINPAGE_FILENAME)
    write_if_different(path, content)
    return path
