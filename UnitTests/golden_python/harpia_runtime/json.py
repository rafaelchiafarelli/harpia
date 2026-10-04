"""JSON for any harpia message, with the C++ target's options.

One message-agnostic module (no per-message wrapper): protobuf's
``json_format`` already works on any message, the same reasoning as the Java
target's ``HarpiaJson``.

- :func:`to_json` matches C++ ``MessageToJsonString`` defaults: lowerCamelCase
  names, proto3 defaults omitted, 64-bit integers as strings, compact
  separators (``{"a":1}``).
- :func:`from_json` ignores keys the schema doesn't know (a newer peer's
  added field), the message-versioning parse-boundary rule, and returns
  ``False`` instead of raising, like the C++ ``bool`` return.

The bar against C++ is cross-parse equality: each side parses the other's
output back to an equal message. Bytes are also identical for every fixture
message (checked 2026-10-04, after matching C++'s ``\u003c``/``\u003e``
escaping of ``<``/``>``); float text could still differ for values whose
shortest representation the two libraries print differently.
"""
import json as _json

from google.protobuf import json_format
from google.protobuf.message import Message


def to_json(msg: Message) -> str:
    """Serialize ``msg`` to compact JSON.

    Args:
        msg: Any protobuf message.

    Returns:
        The JSON text.
    """
    text = _json.dumps(json_format.MessageToDict(msg), separators=(",", ":"),
                       ensure_ascii=False)
    # C++ escapes '<' and '>' inside strings; they can't occur anywhere else
    # in JSON text, so a plain replace matches it byte for byte.
    return text.replace("<", "\\u003c").replace(">", "\\u003e")


def from_json(text: str, msg: Message) -> bool:
    """Replace ``msg``'s contents with the message parsed from ``text``.

    Unknown keys are ignored. On failure ``msg`` is left untouched.

    Args:
        text: JSON text.
        msg: The message to fill.

    Returns:
        ``True`` if ``text`` parsed, ``False`` otherwise.
    """
    parsed = type(msg)()
    try:
        json_format.Parse(text, parsed, ignore_unknown_fields=True)
    except (json_format.Error, ValueError, TypeError):
        return False
    msg.CopyFrom(parsed)
    return True


def is_valid_json(text: str, prototype: Message) -> bool:
    """Whether ``text`` parses as a message of ``prototype``'s type.

    ``prototype`` itself is never modified.
    """
    return from_json(text, type(prototype)())
