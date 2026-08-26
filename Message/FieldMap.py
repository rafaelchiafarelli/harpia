## stable wire-number identity for message fields, frozen across regenerations
#
# Harpia auto-assigns a field's protobuf wire number by declaration order
# (Variables.py:141, var.index = len(self.variables)+1), so inserting or
# deleting any field but the last one silently reassigns every later field's
# number -- an old peer then misreads a newer message's bytes as its own
# field of that number (wrong type/meaning, not a parse error). This module
# freezes each field's number the first time a message ships, into a sidecar
# file, and every later generation reuses/extends that mapping instead of
# recomputing from declaration order. See plans/message-versioning.md S3.
import os
import re

from Errors.Error import Error, Types, Classes
from Util.util import write_if_different

REGISTRY_DIR = "schema_registry"
FIELDMAP_EXT = ".fieldmap"

_FIELD_LINE = re.compile(r'^([A-Za-z_]\w*):(\d+)$')
_RESERVED_LINE = re.compile(r'^#\s*reserved:\s*(.*)$')

# Front-end-injected fields (Variables.py: ID_<md5>, STATUS_<md5>, ERROR_<md5>,
# ORIGINATOR[_<md5>]) carry the whole file's md5 in their own name, which
# changes on ANY edit to the .harpia file -- same convention Database/model.py
# keys off of (_HIDDEN_PREFIXES) for the same reason, duplicated here rather
# than imported since front-end code must not depend on the back-end. Freezing
# by literal name would treat every edit as "the old hidden field was deleted,
# a new one appeared", churning their wire numbers on every regeneration. They
# key by role instead (stable across hash changes); user fields key by their
# own (author-chosen, hash-free) name.
_HIDDEN_PREFIXES = ("ID_", "STATUS_", "ERROR_", "ORIGINATOR")


def _identity(name):
    for prefix in _HIDDEN_PREFIXES:
        if name.startswith(prefix):
            return prefix.rstrip("_")
    return name


def registry_path(harpiaFile, messageName):
    """Sidecar path for one message: schema_registry/<file stem>/<name>.fieldmap,
    next to the declaring .harpia file (NOT under the build/output dir -- that
    gets rmtree'd on a clean regeneration, which would defeat the freeze)."""
    root = os.path.dirname(os.path.abspath(harpiaFile))
    stem = os.path.splitext(os.path.basename(harpiaFile))[0]
    return os.path.join(root, REGISTRY_DIR, stem, messageName + FIELDMAP_EXT)


def _load(path):
    """-> (numbers: {field name: wire number}, reserved: {retired numbers}).
    Both empty when the sidecar doesn't exist yet (first generation)."""
    numbers, reserved = {}, set()
    if not os.path.exists(path):
        return numbers, reserved
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            m = _RESERVED_LINE.match(line)
            if m:
                reserved.update(int(tok) for tok in m.group(1).split(",")
                                if tok.strip())
                continue
            m = _FIELD_LINE.match(line)
            if m:
                numbers[m.group(1)] = int(m.group(2))
    return numbers, reserved


def _save(path, numbers, reserved):
    lines = ["{}:{}".format(name, num)
             for name, num in sorted(numbers.items(), key=lambda kv: kv[1])]
    if reserved:
        lines.append("# reserved: {}".format(
            ",".join(str(n) for n in sorted(reserved))))
    content = "\n".join(lines) + ("\n" if lines else "")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    write_if_different(path, content)


def freeze(variables, harpiaFile, messageName):
    """Assign each variable's stable wire number in place (var.index),
    reading/updating the sidecar fieldmap. Returns None on success, or an
    Error if a field's resolved number lands on a retired (reserved) slot."""
    path = registry_path(harpiaFile, messageName)
    numbers, reserved = _load(path)

    resolved = {}       # variable -> wire number, this generation
    consumedOld = set() # old sidecar names accounted for by a current field

    # Renames first: a renamed_from[old] field inherits old's number: the
    # field is still alive, just under a new name, so its number is not
    # retired, only its old name is. A renamed_from with no matching sidecar
    # entry (first generation for this message, or the name never existed)
    # falls through to plain new-field numbering below -- mirrors
    # Database/MigrationAdapter's own renamed_from handling, which likewise
    # only RENAMEs when the old column is actually there and is a no-op
    # otherwise, rather than treating a not-yet-applicable marker as an error.
    for var in variables:
        if var.renamedFrom is not None and var.renamedFrom in numbers:
            resolved[var] = numbers[var.renamedFrom]
            consumedOld.add(var.renamedFrom)

    # Fields keeping their existing name reuse their existing number.
    for var in variables:
        if var in resolved:
            continue
        key = _identity(var.name)
        if key in numbers:
            resolved[var] = numbers[key]
            consumedOld.add(key)

    # Genuinely new fields: next number never used by a still-live field or
    # a retired one, assigned in declaration order.
    taken = set(numbers.values()) | reserved | set(resolved.values())
    nextNum = (max(taken) + 1) if taken else 1
    for var in variables:
        if var in resolved:
            continue
        while nextNum in taken:
            nextNum += 1
        resolved[var] = nextNum
        taken.add(nextNum)

    # Hard guard: nothing may land on a retired number, however it got
    # there (rename or fresh assignment) -- the direct fix for the silent
    # reuse-after-delete hazard this whole mechanism exists to close.
    for num in resolved.values():
        if num in reserved:
            return Error(errCl=Classes.VARTYPES,
                        errTp=Types.RESERVED_FIELD_NUMBER_REUSED,
                        FileName=harpiaFile,
                        FileLine='0',
                        CharacterNumber='0')

    # Old identities with no current field accounting for them were deleted
    # -- retire their numbers so nothing can silently reuse them later.
    for oldKey, oldNum in numbers.items():
        if oldKey not in consumedOld:
            reserved.add(oldNum)

    for var in variables:
        var.index = resolved[var]

    newNumbers = {_identity(var.name): resolved[var] for var in variables}
    _save(path, newNumbers, reserved)
    return None
