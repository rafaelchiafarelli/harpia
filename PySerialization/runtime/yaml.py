"""YAML for any harpia message: a port of the C++ runtime
``YamlAdapter/runtime/harpia_yaml.h``, byte-identical output. Not PyYAML.

Emitted shape: block style, two-space indent, a top-level mapping with no
wrapper key, strings always double-quoted (escaping ``\\ " \\n \\t``),
``{}`` / ``[]`` for an empty message / list, ``- `` sequences of mappings,
maps as nested mappings. An empty document is ``{}``.

:func:`from_yaml` parses **exactly that subset** (indentation-driven
recursive descent, like the C++ reader) and merges into the message. It
returns ``False`` only when there were lines but none of them matched.
A general YAML parser would accept and emit forms the C++ runtime doesn't,
so the generated project has no ``pyyaml`` dependency.

Same reader rules as C++: the document ``{}`` (what :func:`to_yaml` emits for
an empty message) returns ``True``, and a line is a sequence item only when
its ``-`` is followed by a space or ends the line, so a negative integer map
key (``-5: ...``) reads as a map entry (both formerly differed from C++ or
failed in both: cpp-yaml-empty-mapping-DEFECT,
cpp-yaml-negative-map-keys-DEFECT).
"""
from typing import Any

from google.protobuf.descriptor import FieldDescriptor
from google.protobuf.message import Message

from harpia_runtime.reflect import (
    FD,
    has_presence,
    is_map,
    is_repeated,
    parse_scalar,
    scalar_text,
    set_scalar,
    string_text,
)


def _pad(n: int) -> str:
    return " " * max(n, 0)


def quote(text: str) -> str:
    """Double-quote ``text``, escaping ``\\ " \\n \\t`` like C++ ``quote``."""
    out = ['"']
    for c in text:
        if c == "\\":
            out.append("\\\\")
        elif c == '"':
            out.append('\\"')
        elif c == "\n":
            out.append("\\n")
        elif c == "\t":
            out.append("\\t")
        else:
            out.append(c)
    out.append('"')
    return "".join(out)


def _inline(f: FieldDescriptor, v: Any) -> str:
    if f.cpp_type == FD.CPPTYPE_MESSAGE:
        return ""
    if f.cpp_type == FD.CPPTYPE_STRING:
        return quote(string_text(v))
    return scalar_text(f, v)


def _splice_dash(block: str, dash_indent: int) -> str:
    out: list[str] = []
    pos = 0
    first = True
    while pos <= len(block):
        nl = block.find("\n", pos)
        last = nl == -1
        line = block[pos:] if last else block[pos:nl]
        if not line and last:
            break
        if first:
            strip = min(len(line), dash_indent + 2)
            out.append(_pad(dash_indent) + "- " + line[strip:])
            first = False
        else:
            out.append(line)
        if last:
            break
        out.append("\n")
        pos = nl + 1
    return "".join(out)


def _write_map(msg: Message, f: FieldDescriptor, indent: int, out: list[str]) -> None:
    container = getattr(msg, f.name)
    out.append(_pad(indent) + f.name + ":")
    if len(container) == 0:
        out.append(" {}\n")
        return
    out.append("\n")
    kf = f.message_type.fields_by_name["key"]
    vf = f.message_type.fields_by_name["value"]
    for key in container:
        out.append(_pad(indent + 2) + _inline(kf, key) + ":")
        if vf.cpp_type == FD.CPPTYPE_MESSAGE:
            block: list[str] = []
            _write_message(container[key], indent + 4, block)
            if not block:
                out.append(" {}\n")
            else:
                out.append("\n")
                out.extend(block)
        else:
            out.append(" " + _inline(vf, container[key]) + "\n")


def _write_message(msg: Message, indent: int, out: list[str]) -> None:
    for f in msg.DESCRIPTOR.fields:
        key = f.name
        if is_map(f):
            _write_map(msg, f, indent, out)
            continue
        if is_repeated(f):
            items = getattr(msg, key)
            out.append(_pad(indent) + key + ":")
            if len(items) == 0:
                out.append(" []\n")
                continue
            out.append("\n")
            for item in items:
                if f.cpp_type == FD.CPPTYPE_MESSAGE:
                    block: list[str] = []
                    _write_message(item, indent + 4, block)
                    if not block:
                        out.append(_pad(indent + 2) + "- {}\n")
                    else:
                        out.append(_splice_dash("".join(block), indent + 2))
                else:
                    out.append(_pad(indent + 2) + "- " + _inline(f, item) + "\n")
            continue
        if has_presence(f) and not msg.HasField(key):
            continue
        if f.cpp_type == FD.CPPTYPE_MESSAGE:
            sub: list[str] = []
            _write_message(getattr(msg, key), indent + 2, sub)
            out.append(_pad(indent) + key + ":")
            if not sub:
                out.append(" {}\n")
            else:
                out.append("\n")
                out.extend(sub)
        else:
            out.append(_pad(indent) + key + ": " + _inline(f, getattr(msg, key)) + "\n")


def to_yaml(msg: Message) -> str:
    """Serialize ``msg`` to block-style YAML (``{}`` when empty)."""
    out: list[str] = []
    _write_message(msg, 0, out)
    return "".join(out) or "{}\n"


# ---- read ------------------------------------------------------------------

def _unquote(text: str) -> str:
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        out: list[str] = []
        k = 1
        while k + 1 < len(text):
            c = text[k]
            if c == "\\" and k + 2 < len(text):
                k += 1
                nx = text[k]
                out.append("\n" if nx == "n" else "\t" if nx == "t" else nx)
            else:
                out.append(c)
            k += 1
        return "".join(out)
    return text


def _split_kv(s: str) -> tuple[str, str, bool]:
    if s and s[0] == '"':
        q = 1
        while q < len(s):
            if s[q] == "\\":
                q += 2
            elif s[q] == '"':
                break
            else:
                q += 1
        end = min(q + 1, len(s))
        key = s[:end]
        p = s.find(":", end)
    else:
        p = s.find(":")
        key = s if p == -1 else s[:p]
    if p == -1:
        return key, "", False
    val = s[p + 1:].lstrip(" ")
    return key, val, val != ""


def _mutable(msg: Message, f: FieldDescriptor) -> Message:
    sub: Message = getattr(msg, f.name)
    sub.SetInParent()
    return sub


def _is_seq_item(s: str) -> bool:
    """A sequence item starts with ``-`` followed by a space or the end of
    the line; ``-5: x`` is a map entry with a negative key (as C++
    ``detail::is_seq_item``)."""
    return s.startswith("-") and (len(s) == 1 or s[1] == " ")


class _Reader:
    def __init__(self, text: str) -> None:
        self.lines: list[tuple[int, str]] = []
        for line in text.split("\n"):
            if line.endswith("\r"):
                line = line[:-1]
            ind = len(line) - len(line.lstrip(" "))
            content = line[ind:].rstrip(" \t")
            if content in ("", "---", "..."):
                continue
            self.lines.append((ind, content))
        self.i = 0
        self.hits = 0

    def _at(self, indent: int, dash: bool) -> bool:
        if self.i >= len(self.lines):
            return False
        ind, s = self.lines[self.i]
        return ind == indent and s != "" and _is_seq_item(s) == dash

    def set_scalar(self, msg: Message, f: FieldDescriptor | None, raw: str) -> None:
        if f is None or f.cpp_type == FD.CPPTYPE_MESSAGE:
            return
        value = parse_scalar(f, _unquote(raw))
        if value is None:
            return
        set_scalar(msg, f, value)
        self.hits += 1

    def skip_block(self, indent: int) -> None:
        while self.i < len(self.lines) and self.lines[self.i][0] > indent:
            self.i += 1

    def read_sequence(self, indent: int, msg: Message, f: FieldDescriptor) -> None:
        while self._at(indent, True):
            rest = self.lines[self.i][1][1:].lstrip(" ")
            self.i += 1
            if is_map(f):
                # never emitted by to_yaml: consume the item, set nothing
                self.skip_block(indent)
                continue
            if f.cpp_type != FD.CPPTYPE_MESSAGE:
                if rest and rest != "[]":
                    self.set_scalar(msg, f, rest)
                continue
            item: Message = getattr(msg, f.name).add()
            self.hits += 1
            if rest and rest != "{}":
                key, val, has_val = _split_kv(rest)
                itf = item.DESCRIPTOR.fields_by_name.get(_unquote(key))
                if itf is not None and has_val and val not in ("{}", "[]"):
                    self.set_scalar(item, itf, val)
                elif (itf is not None and not has_val and self.i < len(self.lines)
                        and self.lines[self.i][0] > indent + 2):
                    ci, s = self.lines[self.i]
                    if _is_seq_item(s):
                        self.read_sequence(ci, item, itf)
                    elif itf.cpp_type == FD.CPPTYPE_MESSAGE and not is_repeated(itf):
                        self.read_mapping(ci, _mutable(item, itf))
                    else:
                        self.skip_block(indent + 2)
            self.read_mapping(indent + 2, item)

    def read_map(self, indent: int, msg: Message, f: FieldDescriptor) -> None:
        kf = f.message_type.fields_by_name["key"]
        vf = f.message_type.fields_by_name["value"]
        container = getattr(msg, f.name)
        while self._at(indent, False):
            key, val, has_val = _split_kv(self.lines[self.i][1])
            self.i += 1
            self.hits += 1
            k = parse_scalar(kf, _unquote(key))
            if vf.cpp_type == FD.CPPTYPE_MESSAGE:
                target = container[k]
                target.Clear()
                if (not has_val and self.i < len(self.lines)
                        and self.lines[self.i][0] > indent):
                    self.read_mapping(self.lines[self.i][0], target)
            else:
                value = vf.default_value
                if has_val and val not in ("{}", "[]"):
                    parsed = parse_scalar(vf, _unquote(val))
                    if parsed is not None:
                        value = parsed
                container[k] = value

    def apply_entry(self, indent: int, s: str, msg: Message) -> None:
        key, val, has_val = _split_kv(s)
        f = msg.DESCRIPTOR.fields_by_name.get(_unquote(key))
        if f is None:
            if not has_val:
                self.skip_block(indent)
            return
        if has_val:
            if val not in ("[]", "{}"):
                self.set_scalar(msg, f, val)
            return
        if self.i >= len(self.lines) or self.lines[self.i][0] <= indent:
            return
        child, first = self.lines[self.i]
        if _is_seq_item(first):
            self.read_sequence(child, msg, f)
        elif is_map(f):
            self.read_map(child, msg, f)
        elif f.cpp_type == FD.CPPTYPE_MESSAGE and not is_repeated(f):
            self.read_mapping(child, _mutable(msg, f))
        else:
            self.skip_block(child)

    def read_mapping(self, indent: int, msg: Message) -> None:
        while self._at(indent, False):
            s = self.lines[self.i][1]
            self.i += 1
            self.apply_entry(indent, s, msg)


def from_yaml(text: str, msg: Message) -> bool:
    """Merge the YAML subset :func:`to_yaml` emits into ``msg``.

    Returns:
        ``False`` when the text had content but nothing in it matched a
        field of ``msg``; ``True`` otherwise.
    """
    reader = _Reader(text)
    if reader.lines == [(0, "{}")]:
        return True  # to_yaml's empty document (see the module docstring)
    reader.read_mapping(0, msg)
    return not (reader.lines and reader.hits == 0)
