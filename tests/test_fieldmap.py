"""Unit tests for message.FieldMap -- stable wire-number field identity.

Covers plans/message-versioning.md S3's Foundation slice: field numbers track
a sidecar (schema_registry/<file stem>/<name>.fieldmap), not declaration
order, across regenerations; a deleted field's number is retired (reserved)
and never silently reused; a renamed_from[old] field inherits old's number.

Pure Python, operates on message.Variables.variable directly -- no lexer/
toolchain needed.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
sys.path.insert(0, REPO_ROOT)

from message.FieldMap import freeze, registry_path, _load
from message.Variables import variable


def _var(name, renamedFrom=None):
    v = variable()
    v.name = name
    v.renamedFrom = renamedFrom
    return v


def _numbers(variables):
    return {v.name: v.index for v in variables}


def test_first_generation_freezes_declaration_order(tmp_path):
    harpiaFile = str(tmp_path / "root.harpia")
    fields = [_var("ID_h"), _var("a"), _var("b"), _var("STATUS_h")]
    err = freeze(fields, harpiaFile, "msg")
    assert err is None
    assert _numbers(fields) == {"ID_h": 1, "a": 2, "b": 3, "STATUS_h": 4}

    path = registry_path(harpiaFile, "msg")
    assert os.path.exists(path)
    numbers, reserved = _load(path)
    # hidden fields (ID_/STATUS_/ERROR_/ORIGINATOR) are keyed by role, not
    # their literal (hash-suffixed) name -- see test_hidden_fields_survive_
    # a_hash_change_below for why.
    assert numbers == {"ID": 1, "a": 2, "b": 3, "STATUS": 4}
    assert reserved == set()


def test_second_generation_keeps_numbers_despite_reorder_and_insert(tmp_path):
    harpiaFile = str(tmp_path / "root.harpia")
    gen1 = [_var("ID_h"), _var("a"), _var("b"), _var("STATUS_h")]
    assert freeze(gen1, harpiaFile, "msg") is None

    # second generation: reordered (b before a) and a new field "c" inserted
    # in the middle -- none of this should perturb a/b/ID_h/STATUS_h.
    gen2 = [_var("ID_h"), _var("b"), _var("c"), _var("a"), _var("STATUS_h")]
    assert freeze(gen2, harpiaFile, "msg") is None
    nums = _numbers(gen2)
    assert nums["ID_h"] == 1
    assert nums["a"] == 2
    assert nums["b"] == 3
    assert nums["STATUS_h"] == 4
    # "c" is genuinely new -- gets the next free number, not a declaration-
    # order slot.
    assert nums["c"] == 5


def test_deleted_field_number_is_retired_not_reused(tmp_path):
    harpiaFile = str(tmp_path / "root.harpia")
    gen1 = [_var("ID_h"), _var("a"), _var("b"), _var("STATUS_h")]
    assert freeze(gen1, harpiaFile, "msg") is None

    # "a" (number 2) is deleted; a new field "c" is added.
    gen2 = [_var("ID_h"), _var("b"), _var("c"), _var("STATUS_h")]
    assert freeze(gen2, harpiaFile, "msg") is None
    nums = _numbers(gen2)
    assert nums["b"] == 3
    assert nums["STATUS_h"] == 4
    # "c" must not reuse 2 (a's retired number).
    assert nums["c"] == 5

    _, reserved = _load(registry_path(harpiaFile, "msg"))
    assert reserved == {2}


def test_renamed_from_keeps_old_number(tmp_path):
    harpiaFile = str(tmp_path / "root.harpia")
    gen1 = [_var("ID_h"), _var("handle"), _var("STATUS_h")]
    assert freeze(gen1, harpiaFile, "msg") is None
    handleNum = _numbers(gen1)["handle"]

    gen2 = [_var("ID_h"), _var("label", renamedFrom="handle"), _var("STATUS_h")]
    assert freeze(gen2, harpiaFile, "msg") is None
    assert _numbers(gen2)["label"] == handleNum

    # the old name is gone from the live sidecar, and NOT retired (the field
    # is still alive, just under a new name).
    numbers, reserved = _load(registry_path(harpiaFile, "msg"))
    assert "handle" not in numbers
    assert handleNum not in reserved


def test_renamed_from_unresolvable_falls_back_to_new_field(tmp_path):
    """A renamed_from[old] with no prior sidecar record (first generation, or
    `old` never existed) is not an error -- mirrors MigrationAdapter's own
    renamed_from, which is a no-op when the old column isn't actually live."""
    harpiaFile = str(tmp_path / "root.harpia")
    gen1 = [_var("ID_h"), _var("label", renamedFrom="handle"), _var("STATUS_h")]
    err = freeze(gen1, harpiaFile, "msg")
    assert err is None
    assert _numbers(gen1)["label"] == 2


def test_hidden_fields_survive_a_hash_change(tmp_path):
    """ID_<md5>/STATUS_<md5>/ERROR_<md5>/ORIGINATOR[_<md5>] carry the whole
    file's md5 in their own name (Variables.py), which changes on ANY edit to
    the .harpia file -- even one that doesn't touch these fields at all (e.g.
    reordering unrelated user fields). Freezing by literal name would read
    that as "the old hidden field was deleted, an unrelated new one appeared"
    on every single regeneration; freezing by role must not."""
    harpiaFile = str(tmp_path / "root.harpia")
    gen1 = [_var("ID_aaa"), _var("a"), _var("STATUS_aaa"),
            _var("ERROR_aaa"), _var("ORIGINATOR_aaa")]
    assert freeze(gen1, harpiaFile, "msg") is None
    nums1 = _numbers(gen1)

    # simulates a whole-file hash change (any edit) -- only the hidden
    # fields' names move, "a" is untouched.
    gen2 = [_var("ID_bbb"), _var("a"), _var("STATUS_bbb"),
            _var("ERROR_bbb"), _var("ORIGINATOR_bbb")]
    assert freeze(gen2, harpiaFile, "msg") is None
    nums2 = _numbers(gen2)

    assert nums2["ID_bbb"] == nums1["ID_aaa"]
    assert nums2["a"] == nums1["a"]
    assert nums2["STATUS_bbb"] == nums1["STATUS_aaa"]
    assert nums2["ERROR_bbb"] == nums1["ERROR_aaa"]
    assert nums2["ORIGINATOR_bbb"] == nums1["ORIGINATOR_aaa"]

    _, reserved = _load(registry_path(harpiaFile, "msg"))
    assert reserved == set()


def test_reserved_number_reuse_is_a_hard_error(tmp_path):
    """A hand-tampered (or otherwise corrupted) sidecar that declares a name
    at a number also listed as reserved must hard-error, not silently let a
    field land on a retired slot."""
    harpiaFile = str(tmp_path / "root.harpia")
    path = registry_path(harpiaFile, "msg")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write("a:2\n# reserved: 2\n")

    fields = [_var("a")]
    err = freeze(fields, harpiaFile, "msg")
    assert err is not None
    assert err.errType.name == "RESERVED_FIELD_NUMBER_REUSED"


def test_sidecar_path_mirrors_harpia_file_stem(tmp_path):
    harpiaFile = str(tmp_path / "sub" / "root.harpia")
    path = registry_path(harpiaFile, "msg")
    assert path == str(tmp_path / "sub" / "schema_registry" / "root" / "msg.fieldmap")
